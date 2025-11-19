import json
import numpy as np
import faiss
from PIL import Image
import requests
from io import BytesIO
import torch
from transformers import CLIPProcessor, CLIPModel
import gradio as gr

model = CLIPModel.from_pretrained("patrickjohncyh/fashion-clip")
processor = CLIPProcessor.from_pretrained("patrickjohncyh/fashion-clip", use_fast=True)

print("Loading FAISS indexes and metadata...")
index_male = faiss.read_index("male.faiss")
index_female = faiss.read_index("female.faiss")

with open("male_metadata.json", "r", encoding="utf-8") as f:
    metadata_male = json.load(f)

with open("female_metadata.json", "r", encoding="utf-8") as f:
    metadata_female = json.load(f)

print("FAISS indexes and metadata loaded successfully!")

def truncate_text(text, max_tokens=75):
    tokens = processor.tokenizer.encode(text)
    if len(tokens) > max_tokens:
        tokens = tokens[:max_tokens]
        truncated_text = processor.tokenizer.decode(tokens, skip_special_tokens=True)
        return truncated_text
    return text

def get_image_embedding(image):
    try:
        if isinstance(image, str):
            response = requests.get(image)
            image = Image.open(BytesIO(response.content))
        inputs = processor(images=image, return_tensors="pt", padding=True)
        with torch.no_grad():
            image_features = model.get_image_features(**inputs)
        return image_features.cpu().numpy().flatten()
    except Exception as e:
        print(f"Error processing image: {str(e)}")
        return None

def get_text_embedding(text):
    try:
        truncated_text = truncate_text(text)
        inputs = processor(text=truncated_text, return_tensors="pt", padding=True, truncation=True, max_length=77)
        with torch.no_grad():
            text_features = model.get_text_features(**inputs)
        return text_features.cpu().numpy().flatten()
    except Exception as e:
        print(f"Error processing text: {str(e)}")
        return None

def search_products(gender, image=None, text=None):
    try:
        if gender == "Male":
            index = index_male
            metadata = metadata_male
        else:
            index = index_female
            metadata = metadata_female
        
        image_embedding = get_image_embedding(image) if image is not None else None
        text_embedding = get_text_embedding(text) if text and text.strip() else None
        
        if image_embedding is not None and text_embedding is not None:
            query_embedding = np.concatenate([image_embedding, text_embedding])
        elif image_embedding is not None:
            text_embedding = np.zeros(512)
            query_embedding = np.concatenate([image_embedding, text_embedding])
        elif text_embedding is not None:
            image_embedding = np.zeros(512)
            query_embedding = np.concatenate([image_embedding, text_embedding])
        else:
            return "Please provide at least an image or text"
        
        query_embedding = query_embedding.astype('float32').reshape(1, -1)
        faiss.normalize_L2(query_embedding)
        
        scores, indices = index.search(query_embedding, 3)
        results = []
        for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
            if idx < len(metadata):
                product = metadata[idx]
                results.append({
                    "rank": i + 1,
                    "score": float(score),
                    "title": product.get('pdp_title', ''),
                    "category": product.get('category', ''),
                    "price": product.get('price_sp', ''),
                    "image_url": product.get('image_url', ''),
                    "pdp_url": product.get('pdp_url', ''),
                    "combined_text": product.get('combined_text', '')[:100] + "..." if len(product.get('combined_text', '')) > 100 else product.get('combined_text', '')
                })
        return results
    except Exception as e:
        return f"Error during search: {str(e)}"

def format_results(results):
    if isinstance(results, str):
        return results
    formatted = ""
    for product in results:
        try:
            price = f"{int(product['price']):,}" if product['price'] else "N/A"
        except:
            price = product['price']
        formatted += f"""
<div class="product-card">
    <div class="product-header">
        <span class="rank-badge">#{product['rank']}</span>
        <span class="similarity-score">Similarity: {product['score']:.2%}</span>
    </div>
    <div class="product-info">
        <h3 class="product-title">{product['title']}</h3>
        <div class="product-details">
            <div class="detail-item">
                <strong>Category:</strong> {product['category']}
            </div>
            <div class="detail-item">
                <strong>Price:</strong> {price} VND
            </div>
            <div class="detail-item">
                <strong>Description:</strong> {product['combined_text']}
            </div>
        </div>
        <a href="{product['pdp_url']}" target="_blank" class="product-link">
            View Product
        </a>
    </div>
</div>
"""
    return formatted

def display_images(results):
    if isinstance(results, str):
        return []
    images = []
    for product in results:
        try:
            response = requests.get(product['image_url'])
            img = Image.open(BytesIO(response.content))
            images.append((img, f"#{product['rank']}: {product['title'][:30]}..."))
        except:
            blank_img = Image.new('RGB', (100, 100), color='white')
            images.append((blank_img, f"#{product['rank']}: Cannot load image"))
    return images

def inference_interface(gender, image, text):
    results = search_products(gender, image, text)
    formatted_html = format_results(results)
    images = display_images(results)
    return formatted_html, images

custom_css = """
.product-card {
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    padding: 16px;
    margin: 12px 0;
    background: white;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.product-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(0,0,0,0.15);
}
.product-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #f0f0f0;
}
.rank-badge {
    background: #007bff;
    color: white;
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: bold;
    font-size: 14px;
}
.similarity-score {
    background: #28a745;
    color: white;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 14px;
    font-weight: 500;
}
.product-title {
    color: #333;
    font-size: 16px;
    font-weight: 600;
    margin: 0 0 12px 0;
    line-height: 1.4;
}
.product-details {
    margin-bottom: 12px;
}
.detail-item {
    margin: 6px 0;
    color: #666;
    font-size: 14px;
    line-height: 1.4;
}
.detail-item strong {
    color: #333;
    min-width: 100px;
    display: inline-block;
}
.product-link {
    display: inline-block;
    background: #ff6a00;
    color: white;
    padding: 8px 16px;
    border-radius: 6px;
    text-decoration: none;
    font-weight: 500;
    font-size: 14px;
    transition: background 0.2s ease;
}
.product-link:hover {
    background: #e55a00;
    text-decoration: none;
    color: white;
}
.gallery-container {
    margin-top: 20px;
}
.instructions {
    background: #f8f9fa;
    border-left: 4px solid #007bff;
    padding: 16px;
    margin: 16px 0;
    border-radius: 4px;
}
"""

with gr.Blocks(title="Fashion Product Search", css=custom_css) as demo:
    gr.Markdown("""
    # Fashion Product Search System
    Search fashion products by image or description
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Search")
            gender_radio = gr.Radio(
                choices=["Male", "Female"],
                label="Gender",
                value="Female",
                info="Select gender to filter product search"
            )
            image_input = gr.Image(
                type="pil",
                label="Upload product image",
                sources=["upload", "clipboard", "webcam"],
                height=200
            )
            text_input = gr.Textbox(
                label="Product description",
                placeholder="Example: white t-shirt, black party dress, brown high heels",
                lines=3
            )
            search_btn = gr.Button("Search", variant="primary", size="lg")
            gr.Markdown("""
            <div class="instructions">
            Instructions:<br/>
            • Upload a product image<br/>
            • Or enter product description<br/>
            • Or use both for best results
            </div>
            """)
        
        with gr.Column(scale=2):
            gr.Markdown("### Search Results (Top 3)")
            html_output = gr.HTML(
                label="",
                value="<div style='text-align: center; color: #666; padding: 40px;'>Results will appear here...</div>"
            )
            gr.Markdown("### Product Images")
            gallery_output = gr.Gallery(
                label="",
                show_label=False,
                columns=3,
                height="auto",
                object_fit="contain"
            )
    
    search_btn.click(
        fn=inference_interface,
        inputs=[gender_radio, image_input, text_input],
        outputs=[html_output, gallery_output]
    )
    
    text_input.submit(
        fn=inference_interface,
        inputs=[gender_radio, image_input, text_input],
        outputs=[html_output, gallery_output]
    )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0" if torch.cuda.is_available() else "127.0.0.1",
        share=False,
        show_error=True
    )
