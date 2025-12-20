import json
import os
import re

def clean_text(text):
    if not text:
        return ""
    # Remove multiple spaces and newlines
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def preprocess_opgg_tips(input_file, output_file):
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return

    if not isinstance(data, list):
        print("Error: JSON data is not a list.")
        return

    seen_urls = set()
    seen_content = set() # (title, content)
    unique_data = []
    
    dup_count_url = 0
    dup_count_content = 0
    
    for item in data:
        url = item.get('url')
        title = item.get('title', '')
        content = item.get('content', '')
        
        # Simple cleaning
        title_clean = clean_text(title)
        content_clean = clean_text(content)
        
        # Check URL
        if url in seen_urls:
            dup_count_url += 1
            continue
            
        # Check Title + Content
        content_key = (title_clean, content_clean)
        if content_key in seen_content:
            dup_count_content += 1
            continue
            
        seen_urls.add(url)
        seen_content.add(content_key)
        
        # Create cleaned item
        cleaned_item = item.copy()
        cleaned_item['title'] = title_clean
        cleaned_item['content'] = content_clean
        
        # Clean comments
        if 'comments' in cleaned_item:
            cleaned_comments = []
            for comment in cleaned_item['comments']:
                c_nick = comment.get('nickname')
                c_text = clean_text(comment.get('content', ''))
                if c_text:
                    cleaned_comments.append({
                        "nickname": c_nick,
                        "content": c_text,
                        "date": comment.get('date')
                    })
            cleaned_item['comments'] = cleaned_comments
            
        unique_data.append(cleaned_item)
    
    print(f"Original items: {len(data)}")
    print(f"Duplicates by URL: {dup_count_url}")
    print(f"Duplicates by Title+Content: {dup_count_content}")
    print(f"Total unique items: {len(unique_data)}")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(unique_data, f, ensure_ascii=False, indent=2)
    
    print(f"Saved preprocessed data to {output_file}")

if __name__ == "__main__":
    # Get current script path to determine project root if needed
    # Assuming run from data/ directory
    input_path = 'crawler/opgg/outputs/opgg_tips.json'
    output_path = 'preprocessed/opgg/outputs/preprocessed_opgg_tips.json'
    
    preprocess_opgg_tips(input_path, output_path)
