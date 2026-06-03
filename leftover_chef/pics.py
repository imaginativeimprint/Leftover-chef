# Save as add_sample_images.py
import urllib.request
import os

os.makedirs('/Users/shashankp/documents/projects/leftover_chef/static/images/recipes', exist_ok=True)

# Sample free food images from Unsplash (small sizes for testing)
images = {
    1: 'https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=300&h=300&fit=crop',
    2: 'https://images.unsplash.com/photo-1540420773420-3366772f4999?w=300&h=300&fit=crop',
    3: 'https://images.unsplash.com/photo-1455619452474-d2be8b1e70cd?w=300&h=300&fit=crop',
    4: 'https://images.unsplash.com/photo-1536304993881-ff6e9eefa2a6?w=300&h=300&fit=crop',
    5: 'https://images.unsplash.com/photo-1546094096-0df4bcaaa2e6?w=300&h=300&fit=crop',
    6: 'https://images.unsplash.com/photo-1587731556938-387f00b9a9d6?w=300&h=300&fit=crop',
    7: 'https://images.unsplash.com/photo-1510693206972-df098062cb71?w=300&h=300&fit=crop',
    8: 'https://images.unsplash.com/photo-1518977676601-b53f82aba655?w=300&h=300&fit=crop',
    9: 'https://images.unsplash.com/photo-1547592166-23ac45744acd?w=300&h=300&fit=crop',
    10: 'https://images.unsplash.com/photo-1584271854089-7bb04e4a4d1d?w=300&h=300&fit=crop',
    11: 'https://images.unsplash.com/photo-1604909052743-94e591986f5a?w=300&h=300&fit=crop',
    12: 'https://images.unsplash.com/photo-1603105037889-d5612b3da9b1?w=300&h=300&fit=crop',
}

for recipe_id, url in images.items():
    try:
        urllib.request.urlretrieve(url, f'/Users/shashankp/documents/projects/leftover_chef/static/images/recipes/{recipe_id}.jpg')
        print(f"✅ Downloaded image for recipe {recipe_id}")
    except Exception as e:
        print(f"❌ Failed for recipe {recipe_id}: {e}")

print("\n🎉 All done! You can now run: python3 app.py")