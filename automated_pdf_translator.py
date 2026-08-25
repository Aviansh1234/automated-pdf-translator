import os
import time
import argparse
import shutil
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from pdf2image import convert_from_path
from PIL import Image
import numpy as np
import base64
import requests
import concurrent.futures
import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QProgressBar, QFileDialog, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QAbstractItemView, QSpinBox, QComboBox, QLineEdit, QTabWidget, QSplitter, QFormLayout, QGroupBox, QCheckBox, QDialog, QListView)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap

def pdf_to_images(pdf_path, output_folder, dpi=200):
    os.makedirs(output_folder, exist_ok=True)
    images = convert_from_path(pdf_path, dpi=dpi, fmt='png')
    image_paths = []
    for i, image in enumerate(images):
        if image.mode != 'RGB':
            image = image.convert('RGB')
        img_path = os.path.join(output_folder, f'page_{i+1}.png')
        image.save(img_path, 'PNG')
        image_paths.append(img_path)
    return image_paths

def drag_and_drop_image(driver, image_path):
    with open(image_path, 'rb') as f:
        image_data = f.read()
    b64_image = base64.b64encode(image_data).decode('utf-8')
    file_name = os.path.basename(image_path)
    js = '''
    var b64 = arguments[0];
    var fileName = arguments[1];
    var contentType = 'image/png';
    var byteCharacters = atob(b64);
    var byteNumbers = new Array(byteCharacters.length);
    for (var i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    var byteArray = new Uint8Array(byteNumbers);
    var blob = new Blob([byteArray], {type: contentType});
    var file = new File([blob], fileName, {type: contentType});
    var dt = new DataTransfer();
    dt.items.add(file);
    var dropEvent = new DragEvent('drop', {
        dataTransfer: dt,
        bubbles: true,
        cancelable: true
    });
    var target = document.querySelector('[aria-label="Image translation"]') || document.body;
    target.dispatchEvent(dropEvent);
    '''
    driver.execute_script(js, b64_image, file_name)
    return True

def translate_image(driver, image_path, output_path, source_lang='auto', target_lang='en'):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    try:
        driver.get(f"https://translate.google.com/?sl={source_lang}&tl={target_lang}&op=images&hl=en")
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Accept all')]"))
            ).click()
            time.sleep(1)
        except:
            pass
        drag_and_drop_image(driver, image_path)
        try:
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, 
                    "//div[contains(@class, 'uArJ5e') or "
                    "contains(@class, 'loading') or "
                    "contains(@class, 'progress')]"))
            )
        except TimeoutException:
            pass
        start_time = time.time()
        max_wait = 120
        translated = False
        capture_element = None
        while time.time() - start_time < max_wait:
            try:
                images = driver.find_elements(By.XPATH, "//img[contains(@class, 'Jmlpdc')]")
                largest_img = None
                max_area = 0
                for img in images:
                    if img.is_displayed():
                        size = img.size
                        area = size['width'] * size['height']
                        if area > max_area:
                            max_area = area
                            largest_img = img
                if largest_img:
                    translated = True
                    capture_element = largest_img
                    break
            except Exception:
                pass
            try:
                result_container = driver.find_element(
                    By.XPATH, 
                    "//div[contains(@class, 'result-container') or contains(@class, 'Q4i0jf')]"
                )
                if result_container.is_displayed():
                    try:
                        img = result_container.find_element(By.TAG_NAME, "img")
                        if img.is_displayed():
                            translated = True
                            capture_element = img
                            break
                    except:
                        translated = True
                        capture_element = result_container
                        break
            except Exception:
                pass
            try:
                error_msg = driver.find_element(
                    By.XPATH,
                    "//div[contains(text(), 'error') or contains(text(), 'problem')]"
                )
                if error_msg.is_displayed():
                    return False
            except NoSuchElementException:
                pass
            time.sleep(2)
        if not translated:
            return False
    except Exception:
        return False
    try:
        if capture_element:
            img_src = capture_element.get_attribute('src')
            if img_src and img_src.startswith('data:image'):
                header, encoded = img_src.split(',', 1)
                img_data = base64.b64decode(encoded)
                with open(output_path, 'wb') as f:
                    f.write(img_data)
                if images_are_identical(image_path, output_path):
                    return False
                return True
            elif img_src and img_src.startswith('http'):
                resp = requests.get(img_src)
                if resp.status_code == 200:
                    with open(output_path, 'wb') as f:
                        f.write(resp.content)
                    if images_are_identical(image_path, output_path):
                        return False
                    return True
            elif img_src and img_src.startswith('blob:'):
                js = '''
                var img = arguments[0];
                var canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                var ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                return canvas.toDataURL('image/png');
                '''
                data_url = driver.execute_script(js, capture_element)
                if data_url and data_url.startswith('data:image'):
                    header, encoded = data_url.split(',', 1)
                    img_data = base64.b64decode(encoded)
                    with open(output_path, 'wb') as f:
                        f.write(img_data)
                    if images_are_identical(image_path, output_path):
                        return False
                    return True
        return False
    except Exception:
        return False
    return True

def images_are_identical(img_path1, img_path2):
    try:
        img1 = Image.open(img_path1).convert('RGB')
        img2 = Image.open(img_path2).convert('RGB')
        arr1 = np.array(img1)
        arr2 = np.array(img2)
        return arr1.shape == arr2.shape and np.array_equal(arr1, arr2)
    except Exception:
        return False

def images_to_pdf(image_paths, output_pdf_path):
    if not image_paths:
        raise ValueError("No images to save to PDF")
    imgs = []
    try:
        for p in image_paths:
            im = Image.open(p).convert('RGB')
            imgs.append(im)
        first, rest = imgs[0], imgs[1:]
        first.save(output_pdf_path, "PDF", save_all=True, append_images=rest, resolution=200)
    finally:
        for im in imgs:
            try:
                im.close()
            except Exception:
                pass

def translate_image_worker(args_tuple):
    img_path, translated_path, source_lang, target_lang, max_attempts = args_tuple
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    options.add_argument("--disable-features=ClipboardContentSetting")
    options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.clipboard": 1,
        "profile.content_settings.exceptions.clipboard": {
            "[*.]translate.google.com,*": {"setting": 1}
        }
    })
    options.add_argument("--headless=new")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--window-size=1400,900")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1400, 900)
    driver.set_window_position(0, 0)
    success = False
    try:
        for attempt in range(1, max_attempts + 1):
            if translate_image(driver, img_path, translated_path, source_lang, target_lang):
                success = True
                break
            else:
                if attempt < max_attempts:
                    time.sleep(3)
                    driver.get(f"https://translate.google.com/?sl={source_lang}&tl={target_lang}&op=images&hl=en")
    finally:
        driver.quit()
    return (img_path, translated_path, success)

def translate_image_batch(batch_args):
    batch, source_lang, target_lang, max_attempts = batch_args
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    options.add_argument("--disable-features=ClipboardContentSetting")
    options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.clipboard": 1,
        "profile.content_settings.exceptions.clipboard": {
            "[*.]translate.google.com,*": {"setting": 1}
        }
    })
    options.add_argument("--headless=new")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--window-size=1400,900")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1400, 900)
    driver.set_window_position(0, 0)
    results = []
    try:
        for img_path, translated_path in batch:
            success = False
            attempt = 1
            while True:
                if translate_image(driver, img_path, translated_path, source_lang, target_lang):
                    success = True
                    break
                else:
                    if max_attempts != 0 and attempt >= max_attempts:
                        break
                    print(f"Warning: Retrying translation for {os.path.basename(img_path)} (attempt {attempt+1}{'' if max_attempts == 0 else f'/{max_attempts}'})")
                    time.sleep(3)
                    driver.get(f"https://translate.google.com/?sl={source_lang}&tl={target_lang}&op=images&hl=en")
                    attempt += 1
            results.append((img_path, translated_path, success))
    finally:
        driver.quit()
    return results

def main():
    parser = argparse.ArgumentParser(
        description='Translate a PDF using automatic source-language detection or a specified source language.',
        epilog='Run without command-line arguments to launch the graphical user interface (GUI).'
    )
    parser.add_argument('-i', '--input', required=True, help='Input PDF file path')
    parser.add_argument('-o', '--output', default='translated_output.pdf', help='Output PDF file path')
    parser.add_argument('-s', '--source', default='auto', help='Source language code (default: auto)')
    parser.add_argument('-t', '--target', default='en', help='Target language code (default: en)')
    parser.add_argument('--keep-temp', action='store_true', help='Keep temporary image files')
    parser.add_argument('--dpi', type=int, default=200, help='DPI for image conversion (default: 200)')
    parser.add_argument('--max-attempts', type=int, default=0, help='Max attempts per page (0=∞, default: 0)')
    parser.add_argument('--workers', type=int, default=4, help='Number of concurrent workers (default: 4)')
    args = parser.parse_args()
    if not os.path.isfile(args.input):
        print(f"Error: Input file '{args.input}' not found!")
        return
    temp_folder = 'temp_images'
    translated_folder = 'translated_images'
    os.makedirs(temp_folder, exist_ok=True)
    os.makedirs(translated_folder, exist_ok=True)
    try:
        print(f"Converting '{args.input}' to images with {args.dpi} DPI...")
        original_images = pdf_to_images(args.input, temp_folder, args.dpi)
        print(f"Converted {len(original_images)} pages to images")
        print(f"Translating images in parallel...")
        translated_images = [os.path.join(translated_folder, f'translated_{i+1}.png') for i in range(len(original_images))]
        num_workers = args.workers
        batch_size = (len(original_images) + num_workers - 1) // num_workers
        batches = [
            list(zip(original_images[i*batch_size:(i+1)*batch_size], translated_images[i*batch_size:(i+1)*batch_size]))
            for i in range(num_workers)
        ]
        tasks = [(batch, args.source, args.target, args.max_attempts) for batch in batches if batch]
        success_count = 0
        results = []
        page_counter = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            for batch_result in executor.map(translate_image_batch, tasks):
                for img_path, translated_path, success in batch_result:
                    page_counter += 1
                    print(f"--- Translating page {page_counter}/{len(original_images)} ---")
                    if success:
                        print(f"Page {original_images.index(img_path)+1}: Translation successful!")
                        success_count += 1
                    else:
                        print(f"Page {original_images.index(img_path)+1}: Failed to translate after {args.max_attempts} attempts")
                results.extend(batch_result)
        output_images = []
        for i, (img_path, translated_path, success) in enumerate(results):
            idx = original_images.index(img_path)
            if success:
                output_images.append(translated_images[i])
            else:
                output_images.append(original_images[i])
        if success_count > 0:
            print(f"\nCreating output PDF: '{args.output}'")
            images_to_pdf(output_images, args.output)
            print(f"Successfully translated {success_count}/{len(original_images)} pages")
            print(f"Translation complete! Output saved to '{args.output}'")
        else:
            print("\nError: No pages were translated successfully")
    except Exception as e:
        print(f"\nCritical error: {str(e)}")
    finally:
        if not args.keep_temp:
            print("Cleaning up temporary files and folders...")
            # Remove all files and folders recursively
            for folder in [temp_folder, translated_folder]:
                try:
                    if os.path.exists(folder):
                        shutil.rmtree(folder)
                except Exception as e:
                    print(f"Warning: Could not remove folder {folder}: {e}")

class PagePreviewDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Page Preview")
        self.resize(800, 1000)
        vbox = QVBoxLayout(self)
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(700, 900, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(pixmap)
        vbox.addWidget(label)

class TranslationWorker(QThread):
    page_status_update = pyqtSignal(int, int, str)  # file_idx, page_idx, status
    page_preview_update = pyqtSignal(int, int, str) # file_idx, page_idx, image_path
    file_progress_update = pyqtSignal(int, int, int) # file_idx, done, total
    file_page_count = pyqtSignal(int, int) # file_idx, page_count
    file_done = pyqtSignal(int, str) # file_idx, output_pdf

    def __init__(self, file_idx, pdf_path, output_path, source, target, dpi, max_attempts, workers):
        super().__init__()
        self.file_idx = file_idx
        self.pdf_path = pdf_path
        self.output_path = output_path
        self.source = source
        self.target = target
        self.dpi = dpi
        self.max_attempts = max_attempts
        self.workers = workers

    def run(self):
        self.page_status_update.emit(self.file_idx, -1, 'converting to images')
        temp_folder = f'temp_images_{self.file_idx}'
        translated_folder = f'translated_images_{self.file_idx}'
        os.makedirs(temp_folder, exist_ok=True)
        os.makedirs(translated_folder, exist_ok=True)
        original_images = pdf_to_images(self.pdf_path, temp_folder, self.dpi)
        self.file_page_count.emit(self.file_idx, len(original_images))
        translated_images = [os.path.join(translated_folder, f'translated_{i+1}.png') for i in range(len(original_images))]
        num_workers = self.workers
        batch_size = (len(original_images) + num_workers - 1) // num_workers
        batches = [
            list(zip(original_images[i*batch_size:(i+1)*batch_size], translated_images[i*batch_size:(i+1)*batch_size]))
            for i in range(num_workers)
        ]
        tasks = [(batch, self.source, self.target, self.max_attempts) for batch in batches if batch]
        results = [None] * len(original_images)
        page_status = ['in queue'] * len(original_images)
        def update_status(idx, status):
            self.page_status_update.emit(self.file_idx, idx, status)
        def update_preview(idx, img_path):
            self.page_preview_update.emit(self.file_idx, idx, img_path)
        done = 0
        def process_batch(batch_args):
            batch, source_lang, target_lang, max_attempts = batch_args
            options = webdriver.ChromeOptions()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument("--disable-features=IsolateOrigins,site-per-process")
            options.add_argument("--disable-features=ClipboardContentSetting")
            options.add_experimental_option("prefs", {
                "profile.default_content_setting_values.clipboard": 1,
                "profile.content_settings.exceptions.clipboard": {
                    "[*.]translate.google.com,*": {"setting": 1}
                }
            })
            options.add_argument("--headless=new")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            options.add_argument("--window-size=1400,900")
            driver = webdriver.Chrome(options=options)
            driver.set_window_size(1400, 900)
            driver.set_window_position(0, 0)
            try:
                for img_path, translated_path in batch:
                    idx = original_images.index(img_path)
                    update_status(idx, 'translating')
                    success = False
                    attempt = 1
                    while True:
                        if translate_image(driver, img_path, translated_path, source_lang, target_lang):
                            success = True
                            break
                        else:
                            if max_attempts != 0 and attempt >= max_attempts:
                                break
                            update_status(idx, f'retrying ({attempt+1}{"/∞" if max_attempts==0 else f"/{max_attempts}"})')
                            time.sleep(3)
                            driver.get(f"https://translate.google.com/?sl={source_lang}&tl={target_lang}&op=images&hl=en")
                            attempt += 1
                    if success:
                        update_status(idx, 'translated successfully')
                        update_preview(idx, translated_path)
                        results[idx] = translated_path
                    else:
                        update_status(idx, 'failed')
                        update_preview(idx, img_path)
                        results[idx] = img_path
                    nonlocal done
                    done += 1
                    self.file_progress_update.emit(self.file_idx, done, len(original_images))
            finally:
                driver.quit()
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            executor.map(process_batch, tasks)
        images_to_pdf(results, self.output_path)
        self.file_done.emit(self.file_idx, self.output_path)
        # Remove all files and folders recursively
        for folder in [temp_folder, translated_folder]:
            try:
                if os.path.exists(folder):
                    shutil.rmtree(folder)
            except Exception as e:
                print(f"Warning: Could not remove folder {folder}: {e}")

class PDFStatusDialog(QDialog):
    def __init__(self, fileinfo, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Status: {os.path.basename(fileinfo['file'])}")
        self.resize(700, 500)
        self.layout = QVBoxLayout(self)
        self.page_table = QTableWidget(0, 2)
        self.page_table.setHorizontalHeaderLabels(['Page', 'Status'])
        self.page_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.page_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.page_table.cellDoubleClicked.connect(self.open_page_preview)
        self.layout.addWidget(self.page_table)
        self.fileinfo = fileinfo
        self.refresh_table()
    def refresh_table(self):
        self.page_table.setRowCount(len(self.fileinfo['page_status']))
        for i, (status, img_path) in enumerate(zip(self.fileinfo['page_status'], self.fileinfo['page_preview'])):
            self.page_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
            status_item = QTableWidgetItem(status)
            # Set color based on status
            if status == 'in queue':
                status_item.setBackground(Qt.white)
            elif status == 'translating':
                status_item.setBackground(Qt.lightGray)
            elif status.startswith('retrying'):
                status_item.setBackground(Qt.yellow)
            elif status == 'failed':
                status_item.setBackground(Qt.red)
            elif status == 'translated successfully':
                status_item.setBackground(Qt.green)
            else:
                status_item.setBackground(Qt.white)
            self.page_table.setItem(i, 1, status_item)
    def update_status(self, page_idx, status):
        self.fileinfo['page_status'][page_idx] = status
        self.refresh_table()
    def update_preview(self, page_idx, img_path):
        self.fileinfo['page_preview'][page_idx] = img_path
        self.refresh_table()
    def open_page_preview(self, row, column):
        img_path = self.fileinfo['page_preview'][row]
        if img_path and os.path.exists(img_path):
            dlg = PagePreviewDialog(img_path, self)
            dlg.exec_()

class TranslatorGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Automated PDF Translator')
        self.resize(1200, 700)
        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        self.file_list = []
        self.workers = []
        self.init_main_tab()

    def init_main_tab(self):
        main_tab = QWidget()
        vbox = QVBoxLayout(main_tab)
        # File queue
        self.file_table = QTableWidget(0, 4)
        self.file_table.setHorizontalHeaderLabels(['File', 'Output', 'Progress', 'Status'])
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.cellDoubleClicked.connect(self.open_pdf_status_dialog)
        vbox.addWidget(self.file_table)
        # Controls
        controls = QHBoxLayout()
        self.add_btn = QPushButton('Add PDF(s)')
        self.add_btn.clicked.connect(self.add_files)
        controls.addWidget(self.add_btn)
        # Removed 'Remove Selected' button
        self.start_btn = QPushButton('Start Translation')
        self.start_btn.clicked.connect(self.start_translation)
        controls.addWidget(self.start_btn)
        vbox.addLayout(controls)
        # Settings
        settings = QFormLayout()
        self.dpi_spin = QSpinBox(); self.dpi_spin.setRange(72, 600); self.dpi_spin.setValue(200)
        self.max_attempts_spin = QSpinBox(); self.max_attempts_spin.setRange(0, 1000); self.max_attempts_spin.setValue(0)
        self.workers_spin = QSpinBox(); self.workers_spin.setRange(1, 16); self.workers_spin.setValue(4)
        self.source_edit = QLineEdit('auto')
        self.target_edit = QLineEdit('en')
        settings.addRow('DPI:', self.dpi_spin)
        settings.addRow('Max Attempts (0=∞):', self.max_attempts_spin)
        settings.addRow('Workers (per PDF):', self.workers_spin)
        settings.addRow('Source Language (auto-detect):', self.source_edit)
        settings.addRow('Target Language:', self.target_edit)
        vbox.addLayout(settings)
        self.tabs.addTab(main_tab, 'Main')

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, 'Select PDF files', '', 'PDF Files (*.pdf)')
        for f in files:
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)
            self.file_table.setItem(row, 0, QTableWidgetItem(f))
            output_path = os.path.splitext(f)[0] + '_translated.pdf'
            output_item = QTableWidgetItem(output_path)
            self.file_table.setItem(row, 1, output_item)
            set_output_btn = QPushButton('Set Output')
            set_output_btn.clicked.connect(lambda _, r=row: self.set_output_location(r))
            self.file_table.setCellWidget(row, 1, set_output_btn)
            pb = QProgressBar(); pb.setValue(0)
            self.file_table.setCellWidget(row, 2, pb)
            self.file_table.setItem(row, 3, QTableWidgetItem('in queue'))
            self.file_list.append({
                'file': f,
                'output': output_path,
                'progress': pb,
                'status': 'in queue',
                'page_status': [],
                'page_preview': []
            })

    def set_output_location(self, row):
        fileinfo = self.file_list[row]
        out, _ = QFileDialog.getSaveFileName(self, 'Select Output PDF', fileinfo['output'], 'PDF Files (*.pdf)')
        if out:
            fileinfo['output'] = out
            self.file_table.setItem(row, 1, QTableWidgetItem(out))
            set_output_btn = QPushButton('Set Output')
            set_output_btn.clicked.connect(lambda _, r=row: self.set_output_location(r))
            self.file_table.setCellWidget(row, 1, set_output_btn)

    def start_translation(self):
        for idx, fileinfo in enumerate(self.file_list):
            output_pdf = fileinfo['output']
            worker = TranslationWorker(
                idx, fileinfo['file'], output_pdf,
                self.source_edit.text(), self.target_edit.text(),
                self.dpi_spin.value(), self.max_attempts_spin.value(), self.workers_spin.value()
            )
            worker.page_status_update.connect(self.update_page_status)
            worker.page_preview_update.connect(self.update_page_preview)
            worker.file_progress_update.connect(self.update_file_progress)
            worker.file_page_count.connect(self.init_page_status)
            worker.file_done.connect(self.update_file_done)
            self.workers.append(worker)
            fileinfo['progress'].setMaximum(100)
            worker.start()
    def init_page_status(self, file_idx, page_count):
        self.file_list[file_idx]['page_status'] = ['in queue'] * page_count
        self.file_list[file_idx]['page_preview'] = [None] * page_count
        if self.file_list[file_idx].get('status_dialog'):
            self.file_list[file_idx]['status_dialog'].refresh_table()

    def open_pdf_status_dialog(self, row, column):
        fileinfo = self.file_list[row]
        if not fileinfo.get('status_dialog') or not fileinfo['status_dialog'].isVisible():
            fileinfo['status_dialog'] = PDFStatusDialog(fileinfo, self)
        fileinfo['status_dialog'].refresh_table()
        fileinfo['status_dialog'].show()

    def update_page_status(self, file_idx, page_idx, status):
        if page_idx == -1:
            item = QTableWidgetItem(status)
            # Set color for main table status
            if status == 'in queue':
                item.setBackground(Qt.white)
            elif status == 'converting to images':
                item.setBackground(Qt.lightGray)
            elif status == 'translating':
                item.setBackground(Qt.lightGray)
            elif status.startswith('retrying'):
                item.setBackground(Qt.yellow)
            elif status == 'failed':
                item.setBackground(Qt.red)
            elif status == 'translated successfully' or status == 'Done':
                item.setBackground(Qt.green)
            else:
                item.setBackground(Qt.white)
            self.file_table.setItem(file_idx, 3, item)
            if self.file_list[file_idx].get('status_dialog'):
                self.file_list[file_idx]['status_dialog'].setWindowTitle(f"Status: {os.path.basename(self.file_list[file_idx]['file'])} - {status}")
            return
        self.file_list[file_idx]['page_status'][page_idx] = status
        # Update main table status color for the current page if it's the latest
        item = QTableWidgetItem(status)
        if status == 'in queue':
            item.setBackground(Qt.white)
        elif status == 'translating':
            item.setBackground(Qt.lightGray)
        elif status.startswith('retrying'):
            item.setBackground(Qt.yellow)
        elif status == 'failed':
            item.setBackground(Qt.red)
        elif status == 'translated successfully':
            item.setBackground(Qt.green)
        else:
            item.setBackground(Qt.white)
        self.file_table.setItem(file_idx, 3, item)
        if self.file_list[file_idx].get('status_dialog'):
            self.file_list[file_idx]['status_dialog'].update_status(page_idx, status)

    def update_page_preview(self, file_idx, page_idx, image_path):
        self.file_list[file_idx]['page_preview'][page_idx] = image_path
        if self.file_list[file_idx].get('status_dialog'):
            self.file_list[file_idx]['status_dialog'].update_preview(page_idx, image_path)

    def update_file_progress(self, file_idx, done, total):
        pb = self.file_table.cellWidget(file_idx, 2)
        pb.setValue(int(done / total * 100))

    def update_file_done(self, file_idx, output_pdf):
        self.file_list[file_idx]['output'] = output_pdf
        self.file_table.setItem(file_idx, 3, QTableWidgetItem('Done'))

    # Removed 'remove_selected_files' method

if __name__ == "__main__":
    if len(sys.argv) == 1:
        app = QApplication(sys.argv)
        gui = TranslatorGUI()
        gui.show()
        sys.exit(app.exec_())
    else:
        main()
