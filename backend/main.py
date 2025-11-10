from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from typing import Optional, List
import uuid
from datetime import datetime

# Bildirim oluşturma helper fonksiyonları
async def create_follow_notification(follower_username: str, followed_user_id: str, follower_id: str):
    """Takip bildirimi oluştur"""
    try:
        supabase.table("notifications").insert({
            "user_id": followed_user_id,
            "type": "follow",
            "title": "Yeni Takipçi",
            "message": f"{follower_username} sizi takip etmeye başladı",
            "link": f"/user/{follower_id}"
        }).execute()
    except Exception as e:
        print(f"Bildirim oluşturma hatası: {e}")

async def create_rating_notification(rater_username: str, recipe_owner_id: str, recipe_id: str, recipe_title: str, rating: int):
    """Puanlama bildirimi oluştur"""
    try:
        supabase.table("notifications").insert({
            "user_id": recipe_owner_id,
            "type": "rating",
            "title": "Yeni Değerlendirme",
            "message": f"{rater_username} '{recipe_title}' tarifine {rating} yıldız verdi",
            "link": f"/recipe/{recipe_id}"
        }).execute()
    except Exception as e:
        print(f"Bildirim oluşturma hatası: {e}")

async def create_favorite_notification(favoriter_username: str, recipe_owner_id: str, recipe_id: str, recipe_title: str):
    """Favori bildirimi oluştur"""
    try:
        supabase.table("notifications").insert({
            "user_id": recipe_owner_id,
            "type": "favorite",
            "title": "Tarif Favorilere Eklendi",
            "message": f"{favoriter_username} '{recipe_title}' tarifini favorilerine ekledi",
            "link": f"/recipe/{recipe_id}"
        }).execute()
    except Exception as e:
        print(f"Bildirim oluşturma hatası: {e}")

# .env dosyasını yükle
load_dotenv()

# Supabase bilgilerini kontrol et
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL ve SUPABASE_KEY .env dosyasında tanımlanmalı!")

# FastAPI uygulaması
app = FastAPI(title="Yemek Tarifi API")

# CORS ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase bağlantısı
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Test endpoints
@app.get("/")
async def root():
    return {"message": "Yemek Tarifi API çalışıyor!"}

@app.get("/api/test")
async def test():
    return {"status": "ok", "message": "API bağlantısı başarılı"}

# User search endpoint
@app.get("/api/users/search")
async def search_users(q: str):
    """Kullanıcı ara - username veya full_name ile"""
    try:
        query_lower = q.lower()
        
        # Supabase'de ilike kullanarak arama yap
        result = supabase.table("profiles").select(
            "id, username, full_name, bio, avatar_url"
        ).or_(
            f"username.ilike.%{query_lower}%,full_name.ilike.%{query_lower}%"
        ).limit(20).execute()
        
        # Her kullanıcı için istatistikler ekle
        users_with_stats = []
        for user in result.data:
            # Tarif sayısı
            recipe_count_result = supabase.table("recipes").select("id", count="exact").eq(
                "user_id", user['id']
            ).execute()
            
            # Takipçi sayısı
            followers_result = supabase.table("follows").select("id", count="exact").eq(
                "following_id", user['id']
            ).execute()
            
            user['recipe_count'] = recipe_count_result.count or 0
            user['followers_count'] = followers_result.count or 0
            users_with_stats.append(user)
        
        return {"data": users_with_stats, "count": len(users_with_stats)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Profile endpoints
@app.get("/api/profiles/{user_id}")
async def get_profile(user_id: str):
    """Kullanıcı profilini getir"""
    try:
        result = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
        return {"data": result.data}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Profil bulunamadı: {str(e)}")

@app.put("/api/profiles/{user_id}")
async def update_profile(user_id: str, profile_data: dict):
    """Profil güncelle"""
    try:
        result = supabase.table("profiles").update({
            "username": profile_data.get("username"),
            "full_name": profile_data.get("full_name"),
            "bio": profile_data.get("bio"),
            "avatar_url": profile_data.get("avatar_url")
        }).eq("id", user_id).execute()
        
        return {"message": "Profil güncellendi", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload/avatar")
async def upload_avatar(file: UploadFile = File(...), user_id: str = Form(...)):
    """Avatar yükle"""
    try:
        # Dosya kontrolü
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Sadece resim dosyaları yüklenebilir")
        
        # Dosya boyutu kontrolü (2MB)
        contents = await file.read()
        if len(contents) > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Dosya boyutu 2MB'dan küçük olmalıdır")
        
        # Dosya adı oluştur
        file_ext = file.filename.split('.')[-1]
        file_name = f"avatars/{user_id}-{uuid.uuid4()}.{file_ext}"
        
        # Supabase Storage'a yükle
        supabase.storage.from_("recipe-images").upload(
            file_name,
            contents,
            {"content-type": file.content_type}
        )
        
        # Public URL al
        public_url = supabase.storage.from_("recipe-images").get_public_url(file_name)
        
        return {"url": public_url, "message": "Avatar yüklendi"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload/recipe-images")
async def upload_recipe_images(files: List[UploadFile] = File(...)):
    """Çoklu tarif resmi yükle (max 10)"""
    try:
        if len(files) > 10:
            raise HTTPException(status_code=400, detail="Maksimum 10 resim yüklenebilir")
        
        uploaded_urls = []
        
        for file in files:
            # Dosya kontrolü
            if not file.content_type.startswith('image/'):
                continue
            
            # Dosya boyutu kontrolü (5MB)
            contents = await file.read()
            if len(contents) > 5 * 1024 * 1024:
                continue
            
            # Dosya adı oluştur
            file_ext = file.filename.split('.')[-1]
            file_name = f"recipes/{uuid.uuid4()}.{file_ext}"
            
            # Supabase Storage'a yükle
            supabase.storage.from_("recipe-images").upload(
                file_name,
                contents,
                {"content-type": file.content_type}
            )
            
            # Public URL al
            public_url = supabase.storage.from_("recipe-images").get_public_url(file_name)
            uploaded_urls.append(public_url)
        
        return {"urls": uploaded_urls, "count": len(uploaded_urls), "message": "Resimler yüklendi"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Recipes endpoints - ANONİM KULLANICI DÜZELTMESİ
@app.get("/api/recipes")
async def get_recipes(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: int = 100
):
    """Tüm tarifleri getir - PROFILE BİLGİSİYLE"""
    try:
        query = supabase.table("recipes").select("*")
        
        if category:
            query = query.eq("category", category)
        
        if difficulty:
            query = query.eq("difficulty", difficulty)
        
        result = query.limit(limit).order("created_at", desc=True).execute()
        
        # Her tarif için kullanıcı bilgisini ayrı getir
        recipes_with_users = []
        for recipe in result.data:
            user_profile = {"username": "Anonim", "avatar_url": None}
            
            if recipe.get('user_id'):
                try:
                    profile = supabase.table("profiles").select("username, avatar_url, full_name").eq(
                        "id", recipe['user_id']
                    ).single().execute()
                    
                    if profile.data:
                        user_profile = profile.data
                except Exception as e:
                    print(f"Profil getirme hatası: {e}")
            
            recipe['profile'] = user_profile
            recipes_with_users.append(recipe)
        
        return {"data": recipes_with_users, "count": len(recipes_with_users)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/recipes")
async def create_recipe(recipe_data: dict):
    """Yeni tarif oluştur - ÇOK GÖRSELLE"""
    try:
        # Tarif oluştur
        recipe_result = supabase.table("recipes").insert({
            "user_id": recipe_data["user_id"],
            "title": recipe_data["title"],
            "description": recipe_data["description"],
            "category": recipe_data["category"],
            "difficulty": recipe_data["difficulty"],
            "prep_time": recipe_data["prep_time"],
            "cook_time": recipe_data["cook_time"],
            "servings": recipe_data["servings"],
            "image_url": recipe_data.get("image_urls", [None])[0] if recipe_data.get("image_urls") else None,
            "image_urls": recipe_data.get("image_urls", [])  # Çoklu görsel
        }).execute()
        
        recipe_id = recipe_result.data[0]["id"]
        
        # Malzemeleri ekle
        if recipe_data.get("ingredients"):
            ingredients = [
                {
                    "recipe_id": recipe_id,
                    "name": ing["name"],
                    "quantity": ing["quantity"],
                    "unit": ing["unit"],
                    "order_index": idx + 1
                }
                for idx, ing in enumerate(recipe_data["ingredients"])
            ]
            supabase.table("ingredients").insert(ingredients).execute()
        
        # Adımları ekle
        if recipe_data.get("steps"):
            steps = [
                {
                    "recipe_id": recipe_id,
                    "step_number": idx + 1,
                    "description": step["description"]
                }
                for idx, step in enumerate(recipe_data["steps"])
            ]
            supabase.table("steps").insert(steps).execute()
        
        return {"message": "Tarif oluşturuldu", "data": recipe_result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recipes/{recipe_id}")
async def get_recipe(recipe_id: str):
    """Tek bir tarif getir - PROFILE BİLGİSİYLE"""
    try:
        # Tarif bilgisi
        recipe = supabase.table("recipes").select("*").eq(
            "id", recipe_id
        ).single().execute()
        
        # Kullanıcı profili - DÜZELTME
        user_profile = {"username": "Anonim", "avatar_url": None, "full_name": None}
        if recipe.data.get('user_id'):
            try:
                profile = supabase.table("profiles").select("username, avatar_url, full_name").eq(
                    "id", recipe.data['user_id']
                ).single().execute()
                
                if profile.data:
                    user_profile = profile.data
            except Exception as e:
                print(f"Profil getirme hatası: {e}")
        
        # Malzemeler
        ingredients = supabase.table("ingredients").select("*").eq(
            "recipe_id", recipe_id
        ).order("order_index").execute()
        
        # Adımlar
        steps = supabase.table("steps").select("*").eq(
            "recipe_id", recipe_id
        ).order("step_number").execute()
        
        # Puanlamalar
        ratings = supabase.table("ratings").select("*").eq(
            "recipe_id", recipe_id
        ).execute()
        
        # Her rating için kullanıcı adını getir
        ratings_with_users = []
        for rating in ratings.data:
            try:
                profile = supabase.table("profiles").select("username, avatar_url").eq(
                    "id", rating['user_id']
                ).single().execute()
                
                if profile.data:
                    rating['username'] = profile.data['username']
                    rating['avatar_url'] = profile.data.get('avatar_url')
                else:
                    rating['username'] = "Anonim"
                    rating['avatar_url'] = None
            except:
                rating['username'] = "Anonim"
                rating['avatar_url'] = None
            
            ratings_with_users.append(rating)
        
        # Ortalama puan hesapla
        avg_rating = 0
        if ratings_with_users:
            avg_rating = sum(r['rating'] for r in ratings_with_users) / len(ratings_with_users)
        
        return {
            "recipe": recipe.data,
            "profile": user_profile,
            "ingredients": ingredients.data,
            "steps": steps.data,
            "ratings": ratings_with_users,
            "avg_rating": avg_rating
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/recipes/{recipe_id}")
async def update_recipe(recipe_id: str, recipe_data: dict):
    """Tarif güncelle - ÇOK GÖRSELLE"""
    try:
        # Tarif güncelle
        result = supabase.table("recipes").update({
            "title": recipe_data["title"],
            "description": recipe_data["description"],
            "category": recipe_data["category"],
            "difficulty": recipe_data["difficulty"],
            "prep_time": recipe_data["prep_time"],
            "cook_time": recipe_data["cook_time"],
            "servings": recipe_data["servings"],
            "image_url": recipe_data.get("image_urls", [None])[0] if recipe_data.get("image_urls") else None,
            "image_urls": recipe_data.get("image_urls", [])  # Çoklu görsel
        }).eq("id", recipe_id).execute()
        
        # Eski malzemeleri sil
        supabase.table("ingredients").delete().eq("recipe_id", recipe_id).execute()
        
        # Yeni malzemeleri ekle
        if recipe_data.get("ingredients"):
            ingredients = [
                {
                    "recipe_id": recipe_id,
                    "name": ing["name"],
                    "quantity": ing["quantity"],
                    "unit": ing["unit"],
                    "order_index": idx + 1
                }
                for idx, ing in enumerate(recipe_data["ingredients"])
            ]
            supabase.table("ingredients").insert(ingredients).execute()
        
        # Eski adımları sil
        supabase.table("steps").delete().eq("recipe_id", recipe_id).execute()
        
        # Yeni adımları ekle
        if recipe_data.get("steps"):
            steps = [
                {
                    "recipe_id": recipe_id,
                    "step_number": idx + 1,
                    "description": step["description"]
                }
                for idx, step in enumerate(recipe_data["steps"])
            ]
            supabase.table("steps").insert(steps).execute()
        
        return {"message": "Tarif güncellendi", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/recipes/{recipe_id}")
async def delete_recipe(recipe_id: str):
    """Tarif sil"""
    try:
        # Cascade delete sayesinde ilişkili veriler otomatik silinecek
        result = supabase.table("recipes").delete().eq("id", recipe_id).execute()
        
        return {"message": "Tarif silindi", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/categories")
async def get_categories():
    """Kategori listesi"""
    return {
        "data": [
            "Ana Yemek",
            "Çorba",
            "Salata",
            "Tatlı",
            "İçecek",
            "Aperatif",
            "Kahvaltılık"
        ]
    }

# Favorites endpoints
@app.get("/api/favorites/{user_id}")
async def get_user_favorites(user_id: str):
    """Kullanıcının favorilerini getir"""
    try:
        result = supabase.table("favorites").select(
            "*, recipes(*)"
        ).eq("user_id", user_id).order("created_at", desc=True).execute()
        
        # Her tarif için profil bilgisini ekle
        favorites_with_profiles = []
        for fav in result.data:
            recipe = fav.get('recipes')
            if recipe:
                # Kullanıcı profilini getir
                user_profile = {"username": "Anonim", "avatar_url": None}
                if recipe.get('user_id'):
                    try:
                        profile = supabase.table("profiles").select("username, avatar_url").eq(
                            "id", recipe['user_id']
                        ).single().execute()
                        
                        if profile.data:
                            user_profile = profile.data
                    except:
                        pass
                
                recipe['profile'] = user_profile
                favorites_with_profiles.append({
                    "id": fav['id'],
                    "recipe": recipe,
                    "created_at": fav['created_at']
                })
        
        return {"data": favorites_with_profiles, "count": len(favorites_with_profiles)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/favorites")
async def add_favorite(favorite_data: dict):
    """Favorilere ekle"""
    try:
        result = supabase.table("favorites").insert({
            "user_id": favorite_data["user_id"],
            "recipe_id": favorite_data["recipe_id"]
        }).execute()
        
        # Tarif bilgisini al
        recipe = supabase.table("recipes").select("user_id, title").eq(
            "id", favorite_data["recipe_id"]
        ).single().execute()
        
        # Kullanıcı bilgisini al
        favoriter = supabase.table("profiles").select("username").eq(
            "id", favorite_data["user_id"]
        ).single().execute()
        
        # Bildirim oluştur (kendi tarifini favorilere eklememişse)
        if recipe.data and favoriter.data and recipe.data["user_id"] != favorite_data["user_id"]:
            await create_favorite_notification(
                favoriter.data["username"],
                recipe.data["user_id"],
                favorite_data["recipe_id"],
                recipe.data["title"]
            )
        
        return {"message": "Favorilere eklendi", "data": result.data}
    except Exception as e:
        if "duplicate" in str(e).lower():
            raise HTTPException(status_code=400, detail="Bu tarif zaten favorilerinizde")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/favorites/{user_id}/{recipe_id}")
async def remove_favorite(user_id: str, recipe_id: str):
    """Favorilerden çıkar"""
    try:
        result = supabase.table("favorites").delete().eq(
            "user_id", user_id
        ).eq("recipe_id", recipe_id).execute()
        
        return {"message": "Favorilerden çıkarıldı", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/favorites/check/{user_id}/{recipe_id}")
async def check_favorite(user_id: str, recipe_id: str):
    """Tarif favorilerde mi kontrol et"""
    try:
        result = supabase.table("favorites").select("id").eq(
            "user_id", user_id
        ).eq("recipe_id", recipe_id).execute()
        
        return {"is_favorite": len(result.data) > 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Ratings endpoints
@app.post("/api/ratings")
async def add_rating(rating_data: dict):
    """Puan ve yorum ekle"""
    try:
        existing = supabase.table("ratings").select("id").eq(
            "user_id", rating_data["user_id"]
        ).eq("recipe_id", rating_data["recipe_id"]).execute()
        
        if existing.data:
            result = supabase.table("ratings").update({
                "rating": rating_data["rating"],
                "comment": rating_data.get("comment", "")
            }).eq("user_id", rating_data["user_id"]).eq(
                "recipe_id", rating_data["recipe_id"]
            ).execute()
            message = "Değerlendirme güncellendi"
        else:
            result = supabase.table("ratings").insert({
                "user_id": rating_data["user_id"],
                "recipe_id": rating_data["recipe_id"],
                "rating": rating_data["rating"],
                "comment": rating_data.get("comment", "")
            }).execute()
            message = "Değerlendirme eklendi"
            
            # Bildirim oluştur
            recipe = supabase.table("recipes").select("user_id, title").eq(
                "id", rating_data["recipe_id"]
            ).single().execute()
            
            rater = supabase.table("profiles").select("username").eq(
                "id", rating_data["user_id"]
            ).single().execute()
            
            if recipe.data and rater.data and recipe.data["user_id"] != rating_data["user_id"]:
                await create_rating_notification(
                    rater.data["username"],
                    recipe.data["user_id"],
                    rating_data["recipe_id"],
                    recipe.data["title"],
                    rating_data["rating"]
                )
        
        return {"message": message, "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/ratings/{user_id}/{recipe_id}")
async def delete_rating(user_id: str, recipe_id: str):
    """Puanı sil"""
    try:
        result = supabase.table("ratings").delete().eq(
            "user_id", user_id
        ).eq("recipe_id", recipe_id).execute()
        
        return {"message": "Değerlendirme silindi", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ratings/user/{user_id}/{recipe_id}")
async def get_user_rating(user_id: str, recipe_id: str):
    """Kullanıcının tarif için verdiği puanı getir"""
    try:
        result = supabase.table("ratings").select("*").eq(
            "user_id", user_id
        ).eq("recipe_id", recipe_id).execute()
        
        if result.data:
            return {"data": result.data[0]}
        else:
            return {"data": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Follows endpoints
@app.post("/api/follows")
async def follow_user(follow_data: dict):
    """Kullanıcıyı takip et"""
    try:
        if follow_data["follower_id"] == follow_data["following_id"]:
            raise HTTPException(status_code=400, detail="Kendinizi takip edemezsiniz")
        
        result = supabase.table("follows").insert({
            "follower_id": follow_data["follower_id"],
            "following_id": follow_data["following_id"]
        }).execute()
        
        # Takipçinin kullanıcı adını al
        follower = supabase.table("profiles").select("username").eq(
            "id", follow_data["follower_id"]
        ).single().execute()
        
        # Bildirim oluştur
        if follower.data:
            await create_follow_notification(
                follower.data["username"],
                follow_data["following_id"],
                follow_data["follower_id"]
            )
        
        return {"message": "Takip edildi", "data": result.data}
    except Exception as e:
        if "duplicate" in str(e).lower():
            raise HTTPException(status_code=400, detail="Bu kullanıcıyı zaten takip ediyorsunuz")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/follows/{follower_id}/{following_id}")
async def unfollow_user(follower_id: str, following_id: str):
    """Kullanıcıyı takipten çıkar"""
    try:
        result = supabase.table("follows").delete().eq(
            "follower_id", follower_id
        ).eq("following_id", following_id).execute()
        
        return {"message": "Takipten çıkarıldı", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/follows/check/{follower_id}/{following_id}")
async def check_following(follower_id: str, following_id: str):
    """Takip edilip edilmediğini kontrol et"""
    try:
        result = supabase.table("follows").select("id").eq(
            "follower_id", follower_id
        ).eq("following_id", following_id).execute()
        
        return {"is_following": len(result.data) > 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/follows/followers/{user_id}")
async def get_followers(user_id: str):
    """Kullanıcının takipçilerini getir"""
    try:
        result = supabase.table("follows").select(
            "*, profiles!follows_follower_id_fkey(id, username, avatar_url)"
        ).eq("following_id", user_id).order("created_at", desc=True).execute()
        
        followers = []
        for follow in result.data:
            if follow.get('profiles'):
                followers.append({
                    "id": follow['profiles']['id'],
                    "username": follow['profiles']['username'],
                    "avatar_url": follow['profiles']['avatar_url'],
                    "followed_at": follow['created_at']
                })
        
        return {"data": followers, "count": len(followers)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/follows/following/{user_id}")
async def get_following(user_id: str):
    """Kullanıcının takip ettiklerini getir"""
    try:
        result = supabase.table("follows").select(
            "*, profiles!follows_following_id_fkey(id, username, avatar_url)"
        ).eq("follower_id", user_id).order("created_at", desc=True).execute()
        
        following = []
        for follow in result.data:
            if follow.get('profiles'):
                following.append({
                    "id": follow['profiles']['id'],
                    "username": follow['profiles']['username'],
                    "avatar_url": follow['profiles']['avatar_url'],
                    "followed_at": follow['created_at']
                })
        
        return {"data": following, "count": len(following)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/follows/stats/{user_id}")
async def get_follow_stats(user_id: str):
    """Kullanıcının takipçi ve takip istatistiklerini getir"""
    try:
        # Takipçi sayısı
        followers = supabase.table("follows").select("id", count="exact").eq(
            "following_id", user_id
        ).execute()
        
        # Takip edilen sayısı
        following = supabase.table("follows").select("id", count="exact").eq(
            "follower_id", user_id
        ).execute()
        
        return {
            "followers_count": followers.count or 0,
            "following_count": following.count or 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Notifications endpoints
@app.get("/api/notifications/{user_id}")
async def get_notifications(user_id: str, unread_only: bool = False):
    """Kullanıcının bildirimlerini getir"""
    try:
        query = supabase.table("notifications").select("*").eq("user_id", user_id)
        
        if unread_only:
            query = query.eq("read", False)
        
        result = query.order("created_at", desc=True).limit(50).execute()
        
        return {"data": result.data, "count": len(result.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/notifications/unread/count/{user_id}")
async def get_unread_count(user_id: str):
    """Okunmamış bildirim sayısını getir"""
    try:
        result = supabase.table("notifications").select("id", count="exact").eq(
            "user_id", user_id
        ).eq("read", False).execute()
        
        return {"count": result.count or 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/notifications/{notification_id}/read")
async def mark_notification_as_read(notification_id: str):
    """Bildirimi okundu olarak işaretle"""
    try:
        result = supabase.table("notifications").update({
            "read": True
        }).eq("id", notification_id).execute()
        
        return {"message": "Bildirim okundu olarak işaretlendi", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/notifications/read-all/{user_id}")
async def mark_all_as_read(user_id: str):
    """Tüm bildirimleri okundu olarak işaretle"""
    try:
        result = supabase.table("notifications").update({
            "read": True
        }).eq("user_id", user_id).eq("read", False).execute()
        
        return {"message": "Tüm bildirimler okundu olarak işaretlendi", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/notifications/{notification_id}")
async def delete_notification(notification_id: str):
    """Bildirimi sil"""
    try:
        result = supabase.table("notifications").delete().eq("id", notification_id).execute()
        
        return {"message": "Bildirim silindi", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/notifications/clear/{user_id}")
async def clear_all_notifications(user_id: str):
    """Tüm bildirimleri temizle"""
    try:
        result = supabase.table("notifications").delete().eq("user_id", user_id).execute()
        
        return {"message": "Tüm bildirimler temizlendi", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Search endpoint - ANONİM KULLANICI DÜZELTMESİ
@app.get("/api/recipes/search")
async def search_recipes(
    q: Optional[str] = None,
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    max_time: Optional[int] = None,
    min_rating: Optional[float] = None,
    sort_by: Optional[str] = "created_at",
    order: Optional[str] = "desc",
    limit: int = 20,
    offset: int = 0
):
    """Tariflerde gelişmiş arama"""
    try:
        # Base query
        query = supabase.table("recipes").select("*")
        
        # Kategori filtresi
        if category:
            query = query.eq("category", category)
        
        # Zorluk filtresi
        if difficulty:
            query = query.eq("difficulty", difficulty)
        
        # Maksimum süre filtresi
        if max_time:
            query = query.lte("prep_time", max_time).lte("cook_time", max_time)
        
        # Sıralama
        query = query.order(sort_by, desc=(order == "desc"))
        
        # Pagination
        query = query.range(offset, offset + limit - 1)
        
        result = query.execute()
        
        # Her tarif için kullanıcı bilgisini ekle
        recipes_with_users = []
        for recipe in result.data:
            user_profile = {"username": "Anonim", "avatar_url": None}
            
            if recipe.get('user_id'):
                try:
                    profile = supabase.table("profiles").select("username, avatar_url, full_name").eq(
                        "id", recipe['user_id']
                    ).single().execute()
                    
                    if profile.data:
                        user_profile = profile.data
                except Exception as e:
                    print(f"Profil getirme hatası: {e}")
            
            recipe['profile'] = user_profile
            
            # Metin araması (Python tarafında)
            if q:
                search_text = q.lower()
                title_match = search_text in recipe.get('title', '').lower()
                desc_match = search_text in recipe.get('description', '').lower()
                
                if title_match or desc_match:
                    recipes_with_users.append(recipe)
            else:
                recipes_with_users.append(recipe)
        
        # Minimum rating filtresi
        if min_rating:
            filtered_recipes = []
            for recipe in recipes_with_users:
                ratings = supabase.table("ratings").select("rating").eq(
                    "recipe_id", recipe['id']
                ).execute()
                
                if ratings.data:
                    avg_rating = sum(r['rating'] for r in ratings.data) / len(ratings.data)
                    if avg_rating >= min_rating:
                        filtered_recipes.append(recipe)
                elif min_rating == 0:
                    filtered_recipes.append(recipe)
            
            recipes_with_users = filtered_recipes
        
        return {"data": recipes_with_users, "count": len(recipes_with_users)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Sunucu başlatma komutu için yorum
# uvicorn main:app --reload