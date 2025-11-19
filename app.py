import json
import numpy as np
import faiss
from PIL import Image
import requests
from io import BytesIO
import torch
from transformers import CLIPProcessor, CLIPModel
import gradio as gr

# Load CLIP model
device = "cuda" if torch.cuda.is_available() else "cpu"
model = CLIPModel.from_pretrained("patrickjohncyh/fashion-clip").to(device)
processor = CLIPProcessor.from_pretrained("patrickjohncyh/fashion-clip")

# Load FAISS indexes and metadata
print("Loading FAISS indexes and metadata...")
index_male = faiss.read_index("male.faiss")
index_female = faiss.read_index("female.faiss")

with open("male_metadata.json", "r", encoding="utf-8") as f:
    metadata_male = json.load(f)

with open("female_metadata.json", "r", encoding="utf-8") as f:
    metadata_female = json.load(f)

print("FAISS indexes and metadata loaded successfully!")

def truncate_text(text, max_tokens=75):
    """Truncate text to fit the model token limit"""
    tokens = processor.tokenizer.encode(text)
    if len(tokens) > max_tokens:
        tokens = tokens[:max_tokens]
        truncated_text = processor.tokenizer.decode(tokens, skip_special_tokens=True)
        return truncated_text
    return text

def get_image_embedding(image):
    """Get embedding from image"""
    try:
        if isinstance(image, str):
            response = requests.get(image)
            image = Image.open(BytesIO(response.content))
        
        inputs = processor(images=image, return_tensors="pt", padding=True).to(device)
        with torch.no_grad():
            image_features = model.get_image_features(**inputs)
        return image_features.cpu().numpy().flatten()
    except Exception as e:
        print(f"Error processing image: {str(e)}")
        return None

def get_text_embedding(text):
    """Get embedding from text"""
    try:
        truncated_text = truncate_text(text)
        inputs = processor(text=truncated_text, return_tensors="pt", padding=True, truncation=True, max_length=77).to(device)
        with torch.no_grad():
            text_features = model.get_text_features(**inputs)
        return text_features.cpu().numpy().flatten()
    except Exception as e:
        print(f"Error processing text: {str(e)}")
        return None

def search_products(gender, image=None, text=None):
    """Search products using image and/or text"""
    try:
        if gender == "Male":
            index = index_male
            metadata = metadata_male
        else:
            index = index_female
            metadata = metadata_female
        
        image_embedding = None
        text_embedding = None
        
        if image is not None:
            image_embedding = get_image_embedding(image)
            if image_embedding is None:
                return "Error processing image"
        
        if text and text.strip():
            text_embedding = get_text_embedding(text)
            if text_embedding is None:
                return "Error processing text"
        
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
    """Format search results for display in Gradio"""
    if isinstance(results, str):
        return results
    
    formatted = ""
    for product in results:
        formatted += f"**#{product['rank']} - Similarity: {product['score']:.4f}**\n"
        formatted += f"**Title:** {product['title']}\n"
        formatted += f"**Category:** {product['category']}\n"
        formatted += f"**Price:** {product['price']}\n"
        formatted += f"**Description:** {product['combined_text']}\n"
        formatted += f"**URL:** {product['pdp_url']}\n"
        formatted += "---\n"
    
    return formatted

def display_images(results):
    """Display image results"""
    if isinstance(results, str):
        return []
    
    images = []
    for product in results:
        try:
            response = requests.get(product['image_url'])
            img = Image.open(BytesIO(response.content))
            images.append((img, f"Top {product['rank']}: {product['title'][:30]}..."))
        except:
            blank_img = Image.new('RGB', (100, 100), color='white')
            images.append((blank_img, f"Top {product['rank']}: Cannot load image"))
    
    return images

def inference_interface(gender, image, text):
    """Main inference interface"""
    results = search_products(gender, image, text)
    
    formatted_text = format_results(results)
    images = display_images(results)
    
    return formatted_text, images

with gr.Blocks(title="Fashion Product Search") as demo:
    gr.Markdown("# Fashion Product Search System")
    gr.Markdown("Upload an image, enter a description, or both to search for matching fashion products.")
    
    with gr.Row():
        with gr.Column():
            gender_radio = gr.Radio(
                choices=["Male", "Female"],
                label="Gender",
                value="Female",
                info="Select gender to choose the appropriate FAISS index"
            )
            
            image_input = gr.Image(
                type="pil",
                label="Upload product image",
                sources=["upload", "clipboard"],
                optional=True
            )
            
            text_input = gr.Textbox(
                label="Product description",
                placeholder="Example: white t-shirt, black evening dress...",
                lines=3,
                optional=True
            )
            
            search_btn = gr.Button("Search", variant="primary")
        
        with gr.Column():
            text_output = gr.Textbox(
                label="Search results (Top 3)",
                lines=15,
                max_lines=20
            )
            
            gallery_output = gr.Gallery(
                label="Product images",
                show_label=True,
                columns=3,
                height="auto"
            )
    
    gr.Markdown("## Examples")
    gr.Examples(
        examples=[
            ["Female", None, "black evening dress"],
            ["Male", None, "white office shirt"],
            ["Female", None, "brown high heels"],
            ["Male", None, "blue jeans"]
        ],
        inputs=[gender_radio, image_input, text_input],
        outputs=[text_output, gallery_output],
        fn=inference_interface,
        cache_examples=False
    )
    
    search_btn.click(
        fn=inference_interface,
        inputs=[gender_radio, image_input, text_input],
        outputs=[text_output, gallery_output]
    )
    
    text_input.submit(
        fn=inference_interface,
        inputs=[gender_radio, image_input, text_input],
        outputs=[text_output, gallery_output]
    )

if __Malee__ == "__main__":
    demo.launch(
        server_Malee="0.0.0.0" if torch.cuda.is_available() else "127.0.0.1",
        share=False,
        show_error=True
    )
