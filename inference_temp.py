import torch
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import numpy as np
import os

class FashionCLIPInference:
    def __init__(self, model_path="best_fashion_clip_english"):
        """
        Khởi tạo Fashion CLIP model đã fine-tuned
        
        Args:
            model_path: Đường dẫn đến model đã fine-tuned
        """
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Loading fine-tuned Fashion CLIP from: {model_path}")
        
        # Load model và processor đã fine-tuned
        self.model = CLIPModel.from_pretrained(model_path)
        self.processor = CLIPProcessor.from_pretrained(model_path)
        self.model.to(self.device)
        self.model.eval()
        
        print("Fashion CLIP model loaded successfully!")
        print(f"Model device: {self.device}")
    
    def get_image_embedding(self, image_input):
        """
        Lấy embedding từ ảnh
        
        Args:
            image_input: Có thể là đường dẫn ảnh, PIL Image, hoặc tensor
        
        Returns:
            image_embedding: numpy array shape (1, embedding_dim)
        """
        try:
            # Xử lý đầu vào ảnh
            if isinstance(image_input, str):
                # Nếu là đường dẫn
                image = Image.open(image_input).convert('RGB')
            elif isinstance(image_input, Image.Image):
                # Nếu là PIL Image
                image = image_input
            else:
                raise ValueError("image_input phải là đường dẫn hoặc PIL Image")
            
            # Preprocess ảnh
            inputs = self.processor(images=image, return_tensors="pt")
            pixel_values = inputs['pixel_values'].to(self.device)
            
            # Lấy embedding
            with torch.no_grad():
                image_features = self.model.get_image_features(pixel_values=pixel_values)
                # Chuẩn hóa embedding
                image_embedding = image_features / image_features.norm(dim=-1, keepdim=True)
            
            return image_embedding.cpu().numpy().astype('float32')
            
        except Exception as e:
            print(f"Error getting image embedding: {e}")
            return None
    
    def get_text_embedding(self, text):
        """
        Lấy embedding từ text
        
        Args:
            text: Chuỗi văn bản
        
        Returns:
            text_embedding: numpy array shape (1, embedding_dim)
        """
        try:
            # Preprocess text
            inputs = self.processor(text=[text], return_tensors="pt", padding=True, truncation=True)
            input_ids = inputs['input_ids'].to(self.device)
            attention_mask = inputs['attention_mask'].to(self.device)
            
            # Lấy embedding
            with torch.no_grad():
                text_features = self.model.get_text_features(
                    input_ids=input_ids,
                    attention_mask=attention_mask
                )
                # Chuẩn hóa embedding
                text_embedding = text_features / text_features.norm(dim=-1, keepdim=True)
            
            return text_embedding.cpu().numpy().astype('float32')
            
        except Exception as e:
            print(f"Error getting text embedding: {e}")
            return None
    
    def get_multiple_text_embeddings(self, texts):
        """
        Lấy embedding cho nhiều text cùng lúc
        
        Args:
            texts: List các chuỗi văn bản
        
        Returns:
            text_embeddings: numpy array shape (n_texts, embedding_dim)
        """
        try:
            # Preprocess texts
            inputs = self.processor(text=texts, return_tensors="pt", padding=True, truncation=True)
            input_ids = inputs['input_ids'].to(self.device)
            attention_mask = inputs['attention_mask'].to(self.device)
            
            # Lấy embeddings
            with torch.no_grad():
                text_features = self.model.get_text_features(
                    input_ids=input_ids,
                    attention_mask=attention_mask
                )
                # Chuẩn hóa embeddings
                text_embeddings = text_features / text_features.norm(dim=-1, keepdim=True)
            
            return text_embeddings.cpu().numpy().astype('float32')
            
        except Exception as e:
            print(f"Error getting multiple text embeddings: {e}")
            return None
    
    def compute_similarity(self, image_embedding, text_embedding):
        """
        Tính độ tương đồng giữa image embedding và text embedding
        
        Args:
            image_embedding: embedding của ảnh
            text_embedding: embedding của text
        
        Returns:
            similarity_score: float
        """
        if image_embedding is None or text_embedding is None:
            return 0.0
        
        # Tính cosine similarity
        similarity = np.dot(image_embedding, text_embedding.T)
        return float(similarity[0][0])
    
    def search_by_text(self, query_text, image_embeddings, top_k=5):
        """
        Tìm kiếm ảnh dựa trên text query
        
        Args:
            query_text: text query
            image_embeddings: numpy array của tất cả image embeddings
            top_k: số kết quả trả về
        
        Returns:
            indices: indices của top_k kết quả
            scores: similarity scores
        """
        # Lấy text embedding cho query
        text_embedding = self.get_text_embedding(query_text)
        if text_embedding is None:
            return [], []
        
        # Tính similarity
        similarities = np.dot(image_embeddings, text_embedding.T).flatten()
        
        # Lấy top_k
        top_indices = np.argsort(similarities)[::-1][:top_k]
        top_scores = similarities[top_indices]
        
        return top_indices, top_scores
    
    def search_by_image(self, query_image, text_embeddings, top_k=5):
        """
        Tìm kiếm text dựa trên image query
        
        Args:
            query_image: ảnh query
            text_embeddings: numpy array của tất cả text embeddings
            top_k: số kết quả trả về
        
        Returns:
            indices: indices của top_k kết quả
            scores: similarity scores
        """
        # Lấy image embedding cho query
        image_embedding = self.get_image_embedding(query_image)
        if image_embedding is None:
            return [], []
        
        # Tính similarity
        similarities = np.dot(text_embeddings, image_embedding.T).flatten()
        
        # Lấy top_k
        top_indices = np.argsort(similarities)[::-1][:top_k]
        top_scores = similarities[top_indices]
        
        return top_indices, top_scores

# Ví dụ sử dụng
def demo_inference():
    # Khởi tạo inference
    fashion_clip = FashionCLIPInference("best_fashion_clip_custom")
    
    # Test với ảnh
    image_path = "fashion_dataset/male/2498675246_VNAMZ-12238743780.jpg"
    if os.path.exists(image_path):
        image_embedding = fashion_clip.get_image_embedding(image_path)
        print(f"Image embedding shape: {image_embedding.shape}")
        print(f"Image embedding sample: {image_embedding[0][:5]}")  # Hiển thị 5 giá trị đầu
    else:
        print("Test image not found, using dummy image...")
        # Tạo ảnh dummy để test
        dummy_image = Image.new('RGB', (224, 224), color='red')
        image_embedding = fashion_clip.get_image_embedding(dummy_image)
        print(f"Dummy image embedding shape: {image_embedding.shape}")
    
    # Test với text
    test_texts = [
        "A red t-shirt for men"
    ]
    
    for text in test_texts:
        text_embedding = fashion_clip.get_text_embedding(text)
        if text_embedding is not None:
            print(f"Text: '{text}'")
            print(f"Text embedding shape: {text_embedding.shape}")
            print(f"Text embedding sample: {text_embedding[0][:5]}")
            print("-" * 50)
    
    # Test multiple texts
    multiple_embeddings = fashion_clip.get_multiple_text_embeddings(test_texts)
    if multiple_embeddings is not None:
        print(f"Multiple texts embedding shape: {multiple_embeddings.shape}")

if __name__ == "__main__":
    demo_inference()