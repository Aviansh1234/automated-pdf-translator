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

def main():
    parser = argparse.ArgumentParser(description='Translate PDF from Japanese to English')
    parser.add_argument('-i', '--input', required=True, help='Input PDF file path')
    parser.add_argument('-o', '--output', default='translated_output.pdf', help='Output PDF file path')
    parser.add_argument('-s', '--source', default='ja', help='Source language code (default: ja)')
    parser.add_argument('-t', '--target', default='en', help='Target language code (default: en)')
    parser.add_argument('--keep-temp', action='store_true', help='Keep temporary image files')
    parser.add_argument('--dpi', type=int, default=200, help='DPI for image conversion (default: 200)')
    parser.add_argument('--max-attempts', type=int, default=2, help='Max attempts per page (default: 2)')
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
            print("Cleaning up temporary files...")
            shutil.rmtree(temp_folder, ignore_errors=True)
            shutil.rmtree(translated_folder, ignore_errors=True)

if __name__ == "__main__":
    main()
