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
import threading
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox
import queue

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

def translate_image(driver, image_path, output_path, source_lang='ja', target_lang='en'):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    try:
        driver.get(f"https://translate.google.com/?sl={source_lang}&tl={target_lang}&op=images&hl=en")
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Accept all')]")
            )).click()
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
    images = [Image.open(img) for img in image_paths]
    images[0].save(
        output_pdf_path, save_all=True, append_images=images[1:],
        resolution=200, quality=95
    )

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

class TranslatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Automated PDF Translator")
        self.create_widgets()
        self.translation_thread = None
        self.stop_requested = False

    def create_widgets(self):
        frm = tk.Frame(self.root)
        frm.pack(padx=10, pady=10, fill='x')
        # Input PDF
        tk.Label(frm, text="Input PDF:").grid(row=0, column=0, sticky='e')
        self.input_entry = tk.Entry(frm, width=40)
        self.input_entry.grid(row=0, column=1, sticky='w')
        tk.Button(frm, text="Browse", command=self.browse_input).grid(row=0, column=2)
        # Output PDF
        tk.Label(frm, text="Output PDF:").grid(row=1, column=0, sticky='e')
        self.output_entry = tk.Entry(frm, width=40)
        self.output_entry.grid(row=1, column=1, sticky='w')
        tk.Button(frm, text="Browse", command=self.browse_output).grid(row=1, column=2)
        # Options
        tk.Label(frm, text="DPI:").grid(row=2, column=0, sticky='e')
        self.dpi_var = tk.IntVar(value=200)
        tk.Entry(frm, textvariable=self.dpi_var, width=6).grid(row=2, column=1, sticky='w')
        tk.Label(frm, text="Source Lang:").grid(row=2, column=2, sticky='e')
        self.source_var = tk.StringVar(value='ja')
        tk.Entry(frm, textvariable=self.source_var, width=6).grid(row=2, column=3, sticky='w')
        tk.Label(frm, text="Target Lang:").grid(row=2, column=4, sticky='e')
        self.target_var = tk.StringVar(value='en')
        tk.Entry(frm, textvariable=self.target_var, width=6).grid(row=2, column=5, sticky='w')
        tk.Label(frm, text="Max Attempts (0=∞):").grid(row=3, column=0, sticky='e')
        self.attempts_var = tk.IntVar(value=2)
        tk.Entry(frm, textvariable=self.attempts_var, width=6).grid(row=3, column=1, sticky='w')
        tk.Label(frm, text="Workers:").grid(row=3, column=2, sticky='e')
        self.workers_var = tk.IntVar(value=4)
        tk.Entry(frm, textvariable=self.workers_var, width=6).grid(row=3, column=3, sticky='w')
        self.keep_temp_var = tk.BooleanVar(value=False)
        tk.Checkbutton(frm, text="Keep temp files", variable=self.keep_temp_var).grid(row=3, column=4, columnspan=2, sticky='w')
        # Start button
        self.start_btn = tk.Button(frm, text="Start Translation", command=self.start_translation)
        self.start_btn.grid(row=4, column=0, columnspan=6, pady=5)
        # Progress bar
        self.progress = ttk.Progressbar(self.root, orient='horizontal', length=400, mode='determinate')
        self.progress.pack(pady=5)
        # Status area
        self.status_text = scrolledtext.ScrolledText(self.root, height=12, width=70, state='disabled')
        self.status_text.pack(padx=10, pady=5)

    def browse_input(self):
        path = filedialog.askopenfilename(filetypes=[('PDF Files', '*.pdf')])
        if path:
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, path)

    def browse_output(self):
        path = filedialog.asksaveasfilename(defaultextension='.pdf', filetypes=[('PDF Files', '*.pdf')])
        if path:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, path)

    def log(self, msg):
        self.status_text.config(state='normal')
        self.status_text.insert(tk.END, msg + '\n')
        self.status_text.see(tk.END)
        self.status_text.config(state='disabled')
        self.root.update_idletasks()

    def set_progress(self, value, maxval=None):
        if maxval is not None:
            self.progress['maximum'] = maxval
        self.progress['value'] = value
        self.root.update_idletasks()

    def start_translation(self):
        if self.translation_thread and self.translation_thread.is_alive():
            messagebox.showwarning("Busy", "Translation is already running.")
            return
        self.status_text.config(state='normal')
        self.status_text.delete(1.0, tk.END)
        self.status_text.config(state='disabled')
        self.set_progress(0)
        self.stop_requested = False
        self.progress_queue = queue.Queue()
        self.start_btn.config(state='disabled')
        self.translation_thread = threading.Thread(target=self.run_translation_with_queue)
        self.translation_thread.start()
        self.root.after(100, self.process_progress_queue)

    def process_progress_queue(self):
        try:
            while True:
                msg, progress = self.progress_queue.get_nowait()
                if msg:
                    self.log(msg)
                if progress is not None:
                    if isinstance(progress, tuple):
                        value, maxval = progress
                        self.set_progress(value, maxval)
                    else:
                        self.set_progress(progress)
        except queue.Empty:
            pass
        if self.translation_thread.is_alive():
            self.root.after(100, self.process_progress_queue)
        else:
            self.start_btn.config(state='normal')

    def run_translation_with_queue(self):
        try:
            input_pdf = self.input_entry.get()
            output_pdf = self.output_entry.get()
            dpi = self.dpi_var.get()
            source = self.source_var.get()
            target = self.target_var.get()
            max_attempts = self.attempts_var.get()
            workers = self.workers_var.get()
            keep_temp = self.keep_temp_var.get()
            if not os.path.isfile(input_pdf):
                self.progress_queue.put((f"Error: Input file '{input_pdf}' not found!", None))
                return
            temp_folder = 'temp_images'
            translated_folder = 'translated_images'
            os.makedirs(temp_folder, exist_ok=True)
            os.makedirs(translated_folder, exist_ok=True)
            self.progress_queue.put((f"Converting '{input_pdf}' to images with {dpi} DPI...", None))
            original_images = pdf_to_images(input_pdf, temp_folder, dpi)
            self.progress_queue.put((f"Converted {len(original_images)} pages to images", None))
            self.progress_queue.put((f"Translating images in parallel...", None))
            translated_images = [os.path.join(translated_folder, f'translated_{i+1}.png') for i in range(len(original_images))]
            num_workers = workers
            batch_size = (len(original_images) + num_workers - 1) // num_workers
            batches = [
                list(zip(original_images[i*batch_size:(i+1)*batch_size], translated_images[i*batch_size:(i+1)*batch_size]))
                for i in range(num_workers)
            ]
            tasks = [(batch, source, target, max_attempts) for batch in batches if batch]
            success_count = 0
            results = []
            page_counter = 0
            total_pages = len(original_images)
            self.progress_queue.put((None, (0, total_pages)))
            def gui_batch_callback(batch_result):
                nonlocal page_counter, success_count
                for img_path, translated_path, success in batch_result:
                    page_counter += 1
                    msg = f"--- Translating page {page_counter}/{total_pages} ---"
                    if success:
                        msg += f"\nPage {original_images.index(img_path)+1}: Translation successful!"
                        success_count += 1
                    else:
                        msg += f"\nPage {original_images.index(img_path)+1}: Failed to translate after {max_attempts if max_attempts else '∞'} attempts. Using original page in output PDF."
                    self.progress_queue.put((msg, (page_counter, total_pages)))
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                for batch_result in executor.map(translate_image_batch, tasks):
                    gui_batch_callback(batch_result)
                    results.extend(batch_result)
            output_images = []
            for i, (img_path, translated_path, success) in enumerate(results):
                idx = original_images.index(img_path)
                if success:
                    output_images.append(translated_images[i])
                else:
                    output_images.append(original_images[i])
            if success_count > 0:
                self.progress_queue.put((f"\nCreating output PDF: '{output_pdf}'", None))
                images_to_pdf(output_images, output_pdf)
                self.progress_queue.put((f"Successfully translated {success_count}/{len(original_images)} pages", None))
                self.progress_queue.put((f"Translation complete! Output saved to '{output_pdf}'", None))
            else:
                self.progress_queue.put(("\nError: No pages were translated successfully", None))
        except Exception as e:
            self.progress_queue.put((f"\nCritical error: {str(e)}", None))
        finally:
            if not keep_temp:
                self.progress_queue.put(("Cleaning up temporary files...", None))
                shutil.rmtree('temp_images', ignore_errors=True)
                shutil.rmtree('translated_images', ignore_errors=True)
            self.start_btn.config(state='normal')

def main():
    root = tk.Tk()
    app = TranslatorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
