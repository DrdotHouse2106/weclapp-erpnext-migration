import weclapp as wc
from cache_article_images import download_article_images

def cache_all_wc_data():
    """Cache all data from WeClapp to local database"""
    with wc.WcCacheWrapper() as wrapper:
        wrapper.cache_all()

    # Artikelbilder mit in den Cache laden (rein lesend; auch einzeln ausführbar
    # über cache_article_images.py)
    download_article_images()

if __name__ == "__main__":
    cache_all_wc_data()
