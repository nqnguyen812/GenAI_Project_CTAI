# Lazada Crawler - Python Version

Web crawler để thu thập dữ liệu sản phẩm từ Lazada Vietnam, sử dụng Python với Selenium và undetected-chromedriver để tránh bot detection.

## Tính năng

- 🛡️ **Anti-bot detection** với undetected-chromedriver
- 🔄 **2 chế độ crawl**: URL mode và Category mode
- 🤖 **CAPTCHA handling** (manual solving)
- 📊 **Thu thập dữ liệu đầy đủ**: title, price, description, images, stock
- 💾 **Export JSON** với timestamp
- ⏱️ **Random delays** để giả lập hành vi người dùng

## Cài đặt

### 1. Cài đặt Python Dependencies

```bash
pip install -r requirements.txt
```

Dependencies bao gồm:
- `selenium` - Web automation framework
- `webdriver-manager` - Tự động quản lý ChromeDriver
- `beautifulsoup4` - HTML parsing
- `lxml` - XML/HTML parser
- `undetected-chromedriver` - Chrome driver tránh bot detection

### 2. Cài đặt Chrome Browser

Đảm bảo bạn đã cài đặt Google Chrome trên máy.

## Cách sử dụng

### Mode 1: Crawl theo danh sách URLs

1. **Thêm URLs vào file `lazada_urls.py`**:

```python
LAZADA_URLS = [
    'https://www.lazada.vn/products/...-i123456789.html',
    'https://www.lazada.vn/products/...-i987654321.html',
]
```

2. **Chạy crawler**:

```bash
python lazada_crawler.py
# hoặc
python lazada_crawler.py urls
```

### Mode 2: Crawl theo categories

1. **Cấu hình categories trong `lazada_categories.py`**:

```python
LAZADA_CATEGORIES = [
    {
        'name': 'Trang phục nam',
        'url': 'https://www.lazada.vn/catalog/?q=Trang%20ph%E1%BB%A5c%20nam',
        'maxProducts': 50
    },
    # Thêm categories khác...
]
```

2. **Chạy crawler**:

```bash
python lazada_crawler.py category
# hoặc
python lazada_crawler.py categories
```

## Output

Kết quả được lưu trong thư mục `data/` với format:

```
data/lazada_products_2024-01-15T10-30-45.json
```

### Cấu trúc dữ liệu:

```json
{
  "crawledAt": "2024-01-15T10:30:45",
  "totalProducts": 10,
  "successfulUrls": 9,
  "failedUrls": 1,
  "products": [
    {
      "pdp_url": "https://www.lazada.vn/products/...",
      "pdp_title_value": "Product Title",
      "price_rp": "500000",
      "price_sp": "350000",
      "delivery_time": "1-3 ngày",
      "pdp_desc_value": "Product description...",
      "web_pid": "123456789",
      "vosa": "1",
      "pdp_image_url": "https://...",
      "pdp_image_count": "1",
      "crawledAt": "2024-01-15T10:30:45",
      "execution_time": 5.23,
      "category": "Trang phục nam"
    }
  ],
  "failed": []
}
```

## Giải thích các fields

| Field | Mô tả |
|-------|-------|
| `pdp_url` | URL sản phẩm |
| `pdp_title_value` | Tên sản phẩm |
| `price_rp` | Giá gốc (Regular Price) |
| `price_sp` | Giá sale (Sale Price) |
| `delivery_time` | Thời gian giao hàng |
| `pdp_desc_value` | Mô tả sản phẩm |
| `web_pid` | Product ID / SKU |
| `vosa` | Tình trạng kho (1=còn hàng, 0=hết hàng) |
| `pdp_image_url` | URL hình ảnh chính |
| `pdp_image_count` | Số lượng hình ảnh |
| `execution_time` | Thời gian crawl (giây) |
| `category` | Tên danh mục (nếu crawl theo category) |

## CAPTCHA Handling

Khi gặp CAPTCHA:
1. Crawler sẽ tự động phát hiện và dừng lại
2. Bạn có 60 giây để giải CAPTCHA thủ công trong browser
3. Sau khi giải xong, crawler tự động tiếp tục

## Anti-bot Detection

Crawler sử dụng nhiều kỹ thuật để tránh bị phát hiện:

- ✅ `undetected-chromedriver` - Ẩn dấu hiệu automation
- ✅ Random delays giữa các requests (3-7 giây)
- ✅ Scroll page như người dùng thật
- ✅ Custom headers (Accept-Language, User-Agent)
- ✅ Disable automation flags

## Performance

- **URL mode**: ~15 giây/sản phẩm
- **Category mode**: ~30-90 phút cho 6 categories (50 sản phẩm/category)

## Lưu ý quan trọng

1. **Không chạy quá nhanh** - Tránh bị block IP
2. **Kiểm tra robots.txt** - Tuân thủ quy tắc của website
3. **Sử dụng VPN** (tùy chọn) - Tránh block IP
4. **Backup dữ liệu** - Lưu file JSON thường xuyên

## Troubleshooting

### Lỗi: ChromeDriver not found

```bash
pip install --upgrade webdriver-manager
```

### Lỗi: Bot detection

- Tăng delay time giữa các requests
- Thử sử dụng VPN
- Clear cookies và cache

### Lỗi: CAPTCHA timeout

- Tăng `max_wait_time` trong method `handle_captcha()`
- Giải CAPTCHA nhanh hơn (trong 60 giây)

## So sánh với TypeScript version

| Feature | Python | TypeScript |
|---------|--------|------------|
| Anti-bot | undetected-chromedriver | puppeteer-extra-stealth |
| Performance | Tương đương | Tương đương |
| Setup | Đơn giản hơn | Cần Node.js |
| Ecosystem | Rich libraries | Modern tooling |

## License

MIT License

## Disclaimer

Tool này chỉ dùng cho mục đích học tập và nghiên cứu. Vui lòng tuân thủ Terms of Service của Lazada.