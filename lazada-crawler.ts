import puppeteer from 'puppeteer-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';
import * as cheerio from 'cheerio';
import { writeFileSync, mkdirSync } from 'fs';
import { Page, Browser } from 'puppeteer';

// Add stealth plugin to avoid bot detection
puppeteer.use(StealthPlugin());

// Category configuration
interface Category {
  name: string;
  url: string;
  maxProducts?: number;
}

// Product interface matching Python crawler fields
interface LazadaProduct {
  pdp_url: string;
  pdp_title_value: string;
  price_rp: string;        // Regular price (original price)
  price_sp: string;        // Sale price (current price)
  delivery_time: string;
  pdp_desc_value: string;  // Description
  web_pid: string;         // Product ID
  vosa: string;           // Stock availability (1 = in stock, 0 = out of stock)
  pdp_image_url: string;
  pdp_image_count: string;
  crawledAt: string;
  execution_time: number;
  category?: string;       // Category name (optional)
}

class LazadaCrawler {
  private results: LazadaProduct[] = [];
  private failedUrls: string[] = [];

  /**
   * Random delay to mimic human behavior
   */
  private delay(min: number, max: number): Promise<void> {
    const ms = Math.random() * (max - min) + min;
    return new Promise(resolve => setTimeout(resolve, ms * 1000));
  }

  /**
   * Detect if CAPTCHA is present on the page
   */
  private async detectCaptcha(page: Page): Promise<boolean> {
    try {
      const captchaFrame = await page.$("iframe[src*='captcha']");
      return captchaFrame !== null;
    } catch {
      return false;
    }
  }

  /**
   * Handle CAPTCHA - waits for manual solving or uses extension
   * In the Python code, this uses audio CAPTCHA solving with speech recognition
   * In Node.js, we'll use a simpler approach: detect and wait for manual solving
   */
  private async handleCaptcha(page: Page): Promise<void> {
    console.log('   🤖 CAPTCHA detected!');
    console.log('   ⏳ Please solve the CAPTCHA manually...');
    console.log('   💡 The crawler will wait up to 60 seconds');

    // Wait for CAPTCHA to disappear (max 60 seconds)
    const maxWaitTime = 60000;
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitTime) {
      await this.delay(2, 3);
      const hasCaptcha = await this.detectCaptcha(page);

      if (!hasCaptcha) {
        console.log('   ✅ CAPTCHA solved!');
        await this.delay(2, 3); // Wait for page to fully load
        return;
      }
    }

    throw new Error('CAPTCHA solving timeout');
  }

  /**
   * Scroll page to load all dynamic content
   */
  private async scrollPage(page: Page): Promise<void> {
    await page.evaluate(async () => {
      const scrollHeight = document.body.scrollHeight;
      let currentPosition = 0;
      const step = 200;

      while (currentPosition < scrollHeight) {
        window.scrollTo(0, currentPosition);
        currentPosition += step;
        await new Promise(resolve => setTimeout(resolve, 100));
      }

      // Scroll back to top
      window.scrollTo(0, 0);
    });

    await this.delay(1, 2);
  }

  /**
   * Get product links from a category page
   */
  async getProductLinks(page: Page, categoryUrl: string, maxProducts: number = 50): Promise<string[]> {
    console.log(`   📂 Loading category: ${categoryUrl}`);

    try {
      await page.goto(categoryUrl, {
        waitUntil: 'domcontentloaded',
        timeout: 60000
      });

      await this.delay(3, 5);

      // Check for CAPTCHA
      const hasCaptcha = await this.detectCaptcha(page);
      if (hasCaptcha) {
        await this.handleCaptcha(page);
      }

      // Scroll to load more products
      console.log('   📜 Scrolling to load products...');
      for (let i = 0; i < 5; i++) {
        await page.evaluate(() => {
          window.scrollTo(0, document.body.scrollHeight);
        });
        await this.delay(1, 2);
      }

      // Get HTML and parse with Cheerio
      const html = await page.content();
      const $ = cheerio.load(html);

      console.log('   🔍 Extracting product links...');

      const links: string[] = [];
      const seen = new Set<string>();

      // Lazada uses different selectors for product links
      // Try multiple selectors to find product links
      const selectors = [
        'a[href*="/products/"]',
        '.Bm3ON',
        '[data-tracking="product-card"]',
        '.qmXQo'
      ];

      for (const selector of selectors) {
        $(selector).each((_, el) => {
          const href = $(el).attr('href');
          if (href && href.includes('/products/') && !seen.has(href)) {
            let fullUrl = href;

            // Handle different URL formats
            if (href.startsWith('//')) {
              fullUrl = `https:${href}`;
            } else if (href.startsWith('/')) {
              fullUrl = `https://www.lazada.vn${href}`;
            } else if (!href.startsWith('http')) {
              fullUrl = `https://www.lazada.vn/${href}`;
            }

            // Clean URL - remove query parameters
            const cleanUrl = fullUrl.split('?')[0];

            if (!seen.has(cleanUrl) && cleanUrl.includes('/products/')) {
              links.push(cleanUrl);
              seen.add(cleanUrl);
            }
          }
        });

        if (links.length >= maxProducts) break;
      }

      const productLinks = links.slice(0, maxProducts);
      console.log(`   ✅ Found ${productLinks.length} product links\n`);

      return productLinks;

    } catch (error) {
      console.log(`   ❌ Error getting product links: ${error}`);
      return [];
    }
  }

  /**
   * Extract product title
   */
  private getTitle($: cheerio.CheerioAPI): string {
    try {
      // Try different selectors for Lazada VN
      const selectors = ['.pdp-product-title', 'h1', '.pdp-mod-product-badge-title'];

      for (const selector of selectors) {
        const title = $(selector).first().text().trim();
        if (title && title.length > 10) {
          return title;
        }
      }

      return '';
    } catch {
      return '';
    }
  }

  /**
   * Extract prices (regular and sale price)
   */
  private getPrices($: cheerio.CheerioAPI): { regularPrice: string; salePrice: string } {
    let regularPrice = '';
    let salePrice = '';

    try {
      // For Lazada VN, try multiple approaches
      const priceContainer = $('.pdp-product-price');

      // Try old selectors first (for Indonesia)
      const originBlock = priceContainer.find('.origin-block span').first().text();
      if (originBlock) {
        regularPrice = originBlock.replace(/Rp|₫|[,\s\.]/g, '').trim();
      }

      const salePriceEl = priceContainer.find('.pdp-price_type_normal').first().text();
      if (salePriceEl) {
        salePrice = salePriceEl.replace(/Rp|₫|[,\s\.]/g, '').trim();
      }

      // If not found, try generic price selector for Lazada VN
      if (!regularPrice && !salePrice) {
        const priceText = $('[class*="price"]').first().text();
        // Format: "271.043₫548.772 ₫-51%" or similar
        // Extract numbers with ₫ symbol

        const priceMatches = priceText.match(/[\d\.,]+\s*₫/g);
        if (priceMatches && priceMatches.length >= 1) {
          // First price is usually sale price
          salePrice = priceMatches[0].replace(/₫|[,\s\.]/g, '').trim();

          // Second price (if exists) is regular price
          if (priceMatches.length >= 2) {
            regularPrice = priceMatches[1].replace(/₫|[,\s\.]/g, '').trim();
          }
        }
      }
    } catch {
      // Prices will remain empty
    }

    return { regularPrice, salePrice };
  }

  /**
   * Extract delivery time
   */
  private getDeliveryTime($: cheerio.CheerioAPI): string {
    try {
      const deliveryTime = $('.delivery-option-item__time').first().text().trim();
      return deliveryTime || '';
    } catch {
      return '';
    }
  }

  /**
   * Extract product description from article
   */
  private getDescription($: cheerio.CheerioAPI): string {
    try {
      const descArticle = $('.pdp-product-detail article.lzd-article');
      const paragraphs: string[] = [];

      descArticle.find('p').each((_, el) => {
        const text = $(el).text().replace(/\n/g, '').replace(/- /g, '').trim();
        if (text) {
          paragraphs.push(text);
        }
      });

      return paragraphs.join(', ');
    } catch {
      return '';
    }
  }

  /**
   * Extract data from JSON-LD schema (product ID, images, stock, etc.)
   */
  private getJsonLdData($: cheerio.CheerioAPI): {
    name: string;
    description: string;
    productId: string;
    imageUrl: string;
    stock: string;
    priceFromJson: string;
  } {
    const result = {
      name: '',
      description: '',
      productId: '',
      imageUrl: '',
      stock: '0',
      priceFromJson: ''
    };

    try {
      const jsonLdScript = $('script[type="application/ld+json"]').first().html();
      if (!jsonLdScript) return result;

      const jsonData = JSON.parse(jsonLdScript.replace(/\n/g, ''));

      // Name
      if (jsonData.name) {
        result.name = jsonData.name;
      }

      // Description
      if (jsonData.description) {
        result.description = jsonData.description;
      }

      // Product ID (SKU)
      if (jsonData.sku) {
        result.productId = jsonData.sku;
      }

      // Image URL (can be string or array)
      if (jsonData.image) {
        let imageUrl = '';

        if (typeof jsonData.image === 'string') {
          imageUrl = jsonData.image;
        } else if (Array.isArray(jsonData.image) && jsonData.image.length > 0) {
          imageUrl = jsonData.image[0];
        }

        if (imageUrl) {
          result.imageUrl = imageUrl.startsWith('http')
            ? imageUrl
            : `https:${imageUrl}`;
        }
      }

      // Stock availability
      if (jsonData.offers && jsonData.offers.availability) {
        const availability = jsonData.offers.availability;
        result.stock = (availability.includes('InStock') || availability.includes('LimitedAvailability'))
          ? '1'
          : '0';
      }

      // Price from JSON
      if (jsonData.offers && jsonData.offers.price) {
        result.priceFromJson = String(jsonData.offers.price);
      }

    } catch (error) {
      console.log('   ⚠️  Error parsing JSON-LD:', error);
    }

    return result;
  }

  /**
   * Crawl a single product page
   */
  private async crawlProduct(page: Page, url: string): Promise<LazadaProduct | null> {
    const startTime = Date.now();
    console.log(`   🔍 Crawling: ${url}`);

    try {
      // Navigate to product page
      await page.goto(url, {
        waitUntil: 'domcontentloaded',
        timeout: 60000
      });

      // Wait for page to be fully loaded
      await page.waitForFunction(
        () => document.readyState === 'complete',
        { timeout: 20000 }
      );

      await this.delay(1, 2);

      // Check for CAPTCHA
      const hasCaptcha = await this.detectCaptcha(page);
      if (hasCaptcha) {
        await this.handleCaptcha(page);
        // Wait for page to reload after CAPTCHA
        await page.waitForFunction(
          () => document.readyState === 'complete',
          { timeout: 15000 }
        );
      }

      // Scroll to load all content
      await this.scrollPage(page);

      // Get page HTML
      const html = await page.content();
      const $ = cheerio.load(html);

      // Check if product content is loaded
      const rootElement = $('#root');
      if (rootElement.length === 0) {
        throw new Error('Content not found - possible bot detection');
      }

      // Extract all product data
      const title = this.getTitle($);
      const { regularPrice, salePrice } = this.getPrices($);
      const deliveryTime = this.getDeliveryTime($);
      const description = this.getDescription($);
      const jsonLdData = this.getJsonLdData($);

      // Use fallback data from JSON-LD if HTML extraction failed
      const finalTitle = title || jsonLdData.name;
      const finalDescription = description || jsonLdData.description;
      const finalRegularPrice = regularPrice || jsonLdData.priceFromJson;

      const product: LazadaProduct = {
        pdp_url: url,
        pdp_title_value: finalTitle,
        price_rp: finalRegularPrice,
        price_sp: salePrice,
        delivery_time: deliveryTime,
        pdp_desc_value: finalDescription,
        web_pid: jsonLdData.productId,
        vosa: jsonLdData.stock,
        pdp_image_url: jsonLdData.imageUrl,
        pdp_image_count: jsonLdData.imageUrl ? '1' : '0',
        crawledAt: new Date().toISOString(),
        execution_time: (Date.now() - startTime) / 1000
      };

      console.log(`   ✅ Success: ${finalTitle.substring(0, 50)}...`);
      console.log(`   ⏱️  Time: ${product.execution_time.toFixed(2)}s`);

      return product;

    } catch (error) {
      console.log(`   ❌ Error: ${error}`);
      return null;
    }
  }

  /**
   * Crawl a single category
   */
  async crawlCategory(page: Page, category: Category): Promise<LazadaProduct[]> {
    console.log(`\n📂 Crawling category: ${category.name}`);
    console.log(`🔗 URL: ${category.url}`);

    const categoryProducts: LazadaProduct[] = [];

    try {
      // Get product links from category page
      const productLinks = await this.getProductLinks(
        page,
        category.url,
        category.maxProducts || 50
      );

      if (productLinks.length === 0) {
        console.log(`❌ No products found for ${category.name}\n`);
        return categoryProducts;
      }

      // Crawl each product
      console.log(`   📦 Crawling ${productLinks.length} products...`);

      for (let i = 0; i < productLinks.length; i++) {
        console.log(`   [${i + 1}/${productLinks.length}] Processing product...`);

        const product = await this.crawlProduct(page, productLinks[i]);

        if (product) {
          product.category = category.name; // Add category name
          categoryProducts.push(product);
          this.results.push(product);
        } else {
          this.failedUrls.push(productLinks[i]);
        }

        // Delay between products
        if (i < productLinks.length - 1) {
          const waitTime = Math.floor(Math.random() * 3) + 3;
          console.log(`   ⏳ Waiting ${waitTime}s...`);
          await this.delay(waitTime, waitTime + 2);
        }
      }

      console.log(`   ✅ Completed ${category.name}: ${categoryProducts.length} products\n`);

    } catch (error) {
      console.log(`   ❌ Error crawling category: ${error}\n`);
    }

    return categoryProducts;
  }

  /**
   * Main crawl method - processes list of URLs
   */
  async crawlByUrls(urls: string[]) {
    console.log('🛒 Lazada Crawler Started (URL Mode)');
    console.log('='.repeat(60));
    console.log(`📌 Total URLs: ${urls.length}`);
    console.log(`⏱️  Estimated time: ${(urls.length * 15 / 60).toFixed(1)} minutes\n`);

    const browser: Browser = await puppeteer.launch({
      headless: false,
      executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-blink-features=AutomationControlled',
        '--window-size=1920,1080',
        '--ignore-certificate-errors',
        '--ignore-ssl-errors=yes',
        '--disable-gpu'
      ]
    });

    try {
      const page = await browser.newPage();

      // Set viewport
      await page.setViewport({ width: 1920, height: 1080 });

      // Set extra headers to avoid detection
      await page.setExtraHTTPHeaders({
        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
      });

      // Crawl each URL
      for (let i = 0; i < urls.length; i++) {
        console.log(`\n[${i + 1}/${urls.length}] Processing URL...`);

        const product = await this.crawlProduct(page, urls[i]);

        if (product) {
          this.results.push(product);
        } else {
          this.failedUrls.push(urls[i]);
        }

        // Delay between requests
        if (i < urls.length - 1) {
          const waitTime = Math.floor(Math.random() * 3) + 3;
          console.log(`   ⏳ Waiting ${waitTime}s before next request...`);
          await this.delay(waitTime, waitTime + 2);
        }
      }

      await page.close();

      // Save results
      this.saveResults();

    } catch (error) {
      console.log(`\n❌ Fatal error: ${error}`);
    } finally {
      await browser.close();
      console.log('\n👋 Browser closed');
    }
  }

  /**
   * Main crawl method - processes categories
   */
  async crawlByCategories(categories: Category[]) {
    console.log('🛒 Lazada Crawler Started (Category Mode)');
    console.log('='.repeat(60));
    console.log(`📌 Total categories: ${categories.length}`);
    console.log(`📦 Products per category: ${categories[0]?.maxProducts || 50}`);
    console.log(`⏱️  Estimated time: 30-90 minutes\n`);

    const browser: Browser = await puppeteer.launch({
      headless: false,
      executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-blink-features=AutomationControlled',
        '--window-size=1920,1080',
        '--ignore-certificate-errors',
        '--ignore-ssl-errors=yes',
        '--disable-gpu'
      ]
    });

    try {
      const page = await browser.newPage();

      // Set viewport
      await page.setViewport({ width: 1920, height: 1080 });

      // Set extra headers
      await page.setExtraHTTPHeaders({
        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
      });

      // Crawl each category
      for (const category of categories) {
        await this.crawlCategory(page, category);

        // Delay between categories
        console.log('⏳ Waiting before next category...');
        await this.delay(5, 10);
      }

      await page.close();

      // Save results
      this.saveResults();

    } catch (error) {
      console.log(`\n❌ Fatal error: ${error}`);
    } finally {
      await browser.close();
      console.log('\n👋 Browser closed');
    }
  }

  /**
   * Save crawled data to JSON file
   */
  private saveResults() {
    mkdirSync('data', { recursive: true });

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `data/lazada_products_${timestamp}.json`;

    const output = {
      crawledAt: new Date().toISOString(),
      totalProducts: this.results.length,
      successfulUrls: this.results.length,
      failedUrls: this.failedUrls.length,
      products: this.results,
      failed: this.failedUrls
    };

    writeFileSync(filename, JSON.stringify(output, null, 2), 'utf-8');

    console.log(`\n💾 Results saved to: ${filename}`);
    console.log(`📊 Total products crawled: ${this.results.length}`);
    console.log(`✅ Successful: ${this.results.length}`);
    console.log(`❌ Failed: ${this.failedUrls.length}`);

    if (this.failedUrls.length > 0) {
      console.log('\n⚠️  Failed URLs:');
      this.failedUrls.forEach(url => console.log(`   - ${url}`));
    }
  }
}

// Main execution
async function main() {
  // Check command line arguments
  const args = process.argv.slice(2);
  const mode = args[0] || 'urls'; // Default to URL mode

  const crawler = new LazadaCrawler();

  if (mode === 'categories' || mode === 'category') {
    // Category mode
    let LAZADA_CATEGORIES;

    try {
      const imported = await import('./lazada-categories');
      LAZADA_CATEGORIES = imported.LAZADA_CATEGORIES;

      if (!LAZADA_CATEGORIES || LAZADA_CATEGORIES.length === 0) {
        console.error('❌ Error: No categories found in lazada-categories.ts');
        console.error('💡 Please add categories to lazada-categories.ts');
        process.exit(1);
      }

    } catch (error) {
      console.error('❌ Error: Could not load lazada-categories.ts');
      console.error('💡 Please create lazada-categories.ts with category configuration');
      console.error('📋 Error details:', error);
      process.exit(1);
    }

    // Crawl categories (errors will be caught by the main catch block below)
    await crawler.crawlByCategories(LAZADA_CATEGORIES);

  } else {
    // URL mode (default)
    let LAZADA_URLS;

    try {
      const imported = await import('./lazada-urls');
      LAZADA_URLS = imported.LAZADA_URLS;

      if (!LAZADA_URLS || LAZADA_URLS.length === 0) {
        console.error('❌ Error: No URLs found in lazada-urls.ts');
        console.error('💡 Please add product URLs to lazada-urls.ts');
        process.exit(1);
      }

    } catch (error) {
      console.error('❌ Error: Could not load lazada-urls.ts');
      console.error('💡 Please create lazada-urls.ts with product URLs');
      console.error('📋 Error details:', error);
      process.exit(1);
    }

    // Crawl URLs (errors will be caught by the main catch block below)
    await crawler.crawlByUrls(LAZADA_URLS);
  }
}

// Run crawler
console.log(`
╔═══════════════════════════════════════════════╗
║     Lazada Crawler for Vietnam Market        ║
║                                               ║
║  Usage:                                       ║
║    npm run lazada           (URL mode)        ║
║    npm run lazada category  (Category mode)   ║
╚═══════════════════════════════════════════════╝
`);

main().then(() => {
  console.log('\n✅ Crawling completed!');
  process.exit(0);
}).catch(error => {
  console.error('\n❌ Crawling failed:', error);
  process.exit(1);
});
