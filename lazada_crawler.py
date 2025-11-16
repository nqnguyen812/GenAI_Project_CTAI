#!/usr/bin/env python3

import json
import time
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


class LazadaCrawler:

    def __init__(self):
        self.results = []
        self.failed_urls = []
        self.driver = None

    def delay(self, min_sec: float, max_sec: float):
        time.sleep(random.uniform(min_sec, max_sec))

    def detect_captcha(self) -> bool:
        try:
            captcha_frames = self.driver.find_elements(By.CSS_SELECTOR, "iframe[src*='captcha']")
            return len(captcha_frames) > 0
        except:
            return False

    def handle_captcha(self):
        print('   CAPTCHA detected!')
        print('   Please solve the CAPTCHA manually...')
        print('   The crawler will wait up to 60 seconds')

        max_wait_time = 60
        start_time = time.time()

        while time.time() - start_time < max_wait_time:
            self.delay(2, 3)

            if not self.detect_captcha():
                print('   CAPTCHA solved!')
                self.delay(2, 3)
                return

        raise Exception('CAPTCHA solving timeout')

    def scroll_page(self):
        try:
            scroll_height = self.driver.execute_script("return document.body.scrollHeight")
            current_position = 0
            step = 200

            while current_position < scroll_height:
                self.driver.execute_script(f"window.scrollTo(0, {current_position})")
                current_position += step
                time.sleep(0.1)

            self.driver.execute_script("window.scrollTo(0, 0)")
            self.delay(1, 2)
        except Exception as e:
            print(f'   Scroll error: {e}')

    def get_product_links(self, category_url: str, max_products: int = 50) -> List[str]:
        print(f'   Loading category: {category_url}')

        try:
            self.driver.get(category_url)
            self.delay(3, 5)

            if self.detect_captcha():
                self.handle_captcha()

            print('   Scrolling to load products...')
            for _ in range(5):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                self.delay(1, 2)

            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            print('   Extracting product links...')

            links = []
            seen = set()

            selectors = [
                'a[href*="/products/"]',
                '.Bm3ON',
                '[data-tracking="product-card"]',
                '.qmXQo'
            ]

            for selector in selectors:
                elements = soup.select(selector)

                for el in elements:
                    href = el.get('href', '')

                    if href and '/products/' in href and href not in seen:
                        if href.startswith('//'):
                            full_url = f'https:{href}'
                        elif href.startswith('/'):
                            full_url = f'https://www.lazada.vn{href}'
                        elif not href.startswith('http'):
                            full_url = f'https://www.lazada.vn/{href}'
                        else:
                            full_url = href

                        clean_url = full_url.split('?')[0]

                        if clean_url not in seen and '/products/' in clean_url:
                            links.append(clean_url)
                            seen.add(clean_url)

                if len(links) >= max_products:
                    break

            product_links = links[:max_products]
            print(f'   Found {len(product_links)} product links\n')

            return product_links

        except Exception as e:
            print(f'   Error getting product links: {e}')
            return []

    def get_title(self, soup: BeautifulSoup) -> str:
        try:
            selectors = ['.pdp-product-title', 'h1', '.pdp-mod-product-badge-title']

            for selector in selectors:
                title_el = soup.select_one(selector)
                if title_el:
                    title = title_el.get_text(strip=True)
                    if title and len(title) > 10:
                        return title
            return ''
        except:
            return ''

    def get_prices(self, soup: BeautifulSoup) -> Dict[str, str]:
        regular_price = ''
        sale_price = ''

        try:
            price_container = soup.select_one('.pdp-product-price')

            if price_container:
                origin_block = price_container.select_one('.origin-block span')
                if origin_block:
                    regular_price = origin_block.get_text().replace('Rp', '').replace('₫', '').replace(',', '').replace('.', '').replace(' ', '').strip()

                sale_price_el = price_container.select_one('.pdp-price_type_normal')
                if sale_price_el:
                    sale_price = sale_price_el.get_text().replace('Rp', '').replace('₫', '').replace(',', '').replace('.', '').replace(' ', '').strip()

            if not regular_price and not sale_price:
                price_elements = soup.select('[class*="price"]')
                if price_elements:
                    price_text = price_elements[0].get_text()

                    import re
                    price_matches = re.findall(r'[\d\.,]+\s*₫', price_text)

                    if price_matches and len(price_matches) >= 1:
                        sale_price = price_matches[0].replace('₫', '').replace(',', '').replace('.', '').replace(' ', '').strip()

                        if len(price_matches) >= 2:
                            regular_price = price_matches[1].replace('₫', '').replace(',', '').replace('.', '').replace(' ', '').strip()
        except:
            pass

        return {'regularPrice': regular_price, 'salePrice': sale_price}

    def get_delivery_time(self, soup: BeautifulSoup) -> str:
        try:
            delivery_el = soup.select_one('.delivery-option-item__time')
            if delivery_el:
                return delivery_el.get_text(strip=True)
            return ''
        except:
            return ''

    def get_description(self, soup: BeautifulSoup) -> str:
        try:
            desc_article = soup.select_one('.pdp-product-detail article.lzd-article')
            if desc_article:
                paragraphs = []
                for p in desc_article.select('p'):
                    text = p.get_text().replace('\n', '').replace('- ', '').strip()
                    if text:
                        paragraphs.append(text)
                return ', '.join(paragraphs)
            return ''
        except:
            return ''

    def get_json_ld_data(self, soup: BeautifulSoup) -> Dict:
        result = {
            'name': '',
            'description': '',
            'productId': '',
            'imageUrl': '',
            'stock': '0',
            'priceFromJson': ''
        }

        try:
            json_ld_script = soup.find('script', type='application/ld+json')
            if not json_ld_script:
                return result

            json_data = json.loads(json_ld_script.string.replace('\n', ''))

            if 'name' in json_data:
                result['name'] = json_data['name']

            if 'description' in json_data:
                result['description'] = json_data['description']

            if 'sku' in json_data:
                result['productId'] = json_data['sku']

            if 'image' in json_data:
                image = json_data['image']
                if isinstance(image, str):
                    image_url = image
                elif isinstance(image, list) and len(image) > 0:
                    image_url = image[0]
                else:
                    image_url = ''

                if image_url:
                    result['imageUrl'] = image_url if image_url.startswith('http') else f'https:{image_url}'

            if 'offers' in json_data and 'availability' in json_data['offers']:
                availability = json_data['offers']['availability']
                result['stock'] = '1' if ('InStock' in availability or 'LimitedAvailability' in availability) else '0'

            if 'offers' in json_data and 'price' in json_data['offers']:
                result['priceFromJson'] = str(json_data['offers']['price'])

        except Exception as e:
            print(f'   Error parsing JSON-LD: {e}')

        return result

    def crawl_product(self, url: str) -> Optional[Dict]:
        start_time = time.time()
        print(f'   Crawling: {url}')

        try:
            self.driver.get(url)

            WebDriverWait(self.driver, 20).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )

            self.delay(1, 2)

            if self.detect_captcha():
                self.handle_captcha()
                WebDriverWait(self.driver, 15).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )

            self.scroll_page()

            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            root_element = soup.select_one('#root')
            if not root_element:
                raise Exception('Content not found - possible bot detection')

            title = self.get_title(soup)
            prices = self.get_prices(soup)
            delivery_time = self.get_delivery_time(soup)
            description = self.get_description(soup)
            json_ld_data = self.get_json_ld_data(soup)

            final_title = title or json_ld_data['name']
            final_description = description or json_ld_data['description']
            final_regular_price = prices['regularPrice'] or json_ld_data['priceFromJson']

            product = {
                'pdp_url': url,
                'pdp_title_value': final_title,
                'price_rp': final_regular_price,
                'price_sp': prices['salePrice'],
                'delivery_time': delivery_time,
                'pdp_desc_value': final_description,
                'web_pid': json_ld_data['productId'],
                'vosa': json_ld_data['stock'],
                'pdp_image_url': json_ld_data['imageUrl'],
                'pdp_image_count': '1' if json_ld_data['imageUrl'] else '0',
                'crawledAt': datetime.now().isoformat(),
                'execution_time': round(time.time() - start_time, 2)
            }

            print(f'   Success: {final_title[:50]}...')
            print(f'   Time: {product["execution_time"]}s')

            return product

        except Exception as e:
            print(f'   Error: {e}')
            return None

    def crawl_category(self, category: Dict) -> List[Dict]:
        print(f'\nCrawling category: {category["name"]}')
        print(f'URL: {category["url"]}')

        category_products = []

        try:
            product_links = self.get_product_links(
                category['url'],
                category.get('maxProducts', 50)
            )

            if not product_links:
                print(f'No products found for {category["name"]}\n')
                return category_products

            print(f'   Crawling {len(product_links)} products...')

            for i, link in enumerate(product_links):
                print(f'   [{i+1}/{len(product_links)}] Processing product...')

                product = self.crawl_product(link)

                if product:
                    product['category'] = category['name']
                    category_products.append(product)
                    self.results.append(product)
                else:
                    self.failed_urls.append(link)

                if i < len(product_links) - 1:
                    wait_time = random.randint(3, 5)
                    print(f'   Waiting {wait_time}s...')
                    self.delay(wait_time, wait_time + 2)

            print(f'   Completed {category["name"]}: {len(category_products)} products\n')

        except Exception as e:
            print(f'   Error crawling category: {e}\n')

        return category_products

    def crawl_by_urls(self, urls: List[str]):
        print('Lazada Crawler Started (URL Mode)')
        print('=' * 60)
        print(f'Total URLs: {len(urls)}')
        print(f'Estimated time: {len(urls) * 15 / 60:.1f} minutes\n')

        options = uc.ChromeOptions()
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--ignore-ssl-errors=yes')

        self.driver = uc.Chrome(options=options)

        try:
            self.driver.set_window_size(1920, 1080)

            for i, url in enumerate(urls):
                print(f'\n[{i+1}/{len(urls)}] Processing URL...')

                product = self.crawl_product(url)

                if product:
                    self.results.append(product)
                else:
                    self.failed_urls.append(url)

                if i < len(urls) - 1:
                    wait_time = random.randint(3, 5)
                    print(f'   Waiting {wait_time}s before next request...')
                    self.delay(wait_time, wait_time + 2)

            self.save_results()

        except Exception as e:
            print(f'\nFatal error: {e}')
        finally:
            if self.driver:
                self.driver.quit()
                print('\nBrowser closed')

    def crawl_by_categories(self, categories: List[Dict]):
        print('Lazada Crawler Started (Category Mode)')
        print('=' * 60)
        print(f'Total categories: {len(categories)}')
        print(f'Products per category: {categories[0].get("maxProducts", 50) if categories else 50}')
        print(f'Estimated time: 30-90 minutes\n')

        options = uc.ChromeOptions()
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--ignore-ssl-errors=yes')

        self.driver = uc.Chrome(options=options)

        try:
            self.driver.set_window_size(1920, 1080)

            for category in categories:
                self.crawl_category(category)

                print('Waiting before next category...')
                self.delay(5, 10)

            self.save_results()

        except Exception as e:
            print(f'\nFatal error: {e}')
        finally:
            if self.driver:
                self.driver.quit()
                print('\nBrowser closed')

    def save_results(self):
        Path('data').mkdir(exist_ok=True)

        timestamp = datetime.now().isoformat().replace(':', '-').replace('.', '-')
        filename = f'data/lazada_products_{timestamp}.json'

        output = {
            'crawledAt': datetime.now().isoformat(),
            'totalProducts': len(self.results),
            'successfulUrls': len(self.results),
            'failedUrls': len(self.failed_urls),
            'products': self.results,
            'failed': self.failed_urls
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f'\nResults saved to: {filename}')
        print(f'Total products crawled: {len(self.results)}')
        print(f'Successful: {len(self.results)}')
        print(f'Failed: {len(self.failed_urls)}')

        if self.failed_urls:
            print('\nFailed URLs:')
            for url in self.failed_urls:
                print(f'   - {url}')


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'urls'

    crawler = LazadaCrawler()

    if mode in ['categories', 'category']:
        try:
            from lazada_categories import LAZADA_CATEGORIES

            if not LAZADA_CATEGORIES:
                print('Error: No categories found in lazada_categories.py')
                print('Please add categories to lazada_categories.py')
                sys.exit(1)

            crawler.crawl_by_categories(LAZADA_CATEGORIES)

        except ImportError:
            print('Error: Could not load lazada_categories.py')
            print('Please create lazada_categories.py with category configuration')
            sys.exit(1)
    else:
        try:
            from lazada_urls import LAZADA_URLS

            if not LAZADA_URLS:
                print('Error: No URLs found in lazada_urls.py')
                print('Please add product URLs to lazada_urls.py')
                sys.exit(1)

            crawler.crawl_by_urls(LAZADA_URLS)

        except ImportError:
            print('Error: Could not load lazada_urls.py')
            print('Please create lazada_urls.py with product URLs')
            sys.exit(1)


if __name__ == '__main__':
    print("""
===============================================
     Lazada Crawler for Vietnam Market

  Usage:
    python lazada_crawler.py          (URLs)
    python lazada_crawler.py category
===============================================
    """)

    try:
        main()
        print('\nCrawling completed!')
    except KeyboardInterrupt:
        print('\nCrawling interrupted by user')
        sys.exit(1)
    except Exception as e:
        print(f'\nCrawling failed: {e}')
        sys.exit(1)
