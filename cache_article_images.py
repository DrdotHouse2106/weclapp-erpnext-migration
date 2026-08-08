"""Downloads ALL article images from WeClapp into the local cache - and nothing else.

Standalone, strictly READ-ONLY against WeClapp (only GET requests, no data is ever
modified). Intended to be run manually with a (read-only) API token:

    1. Enter a valid WC_API_TOKEN in config.py
    2. python3 cache_article_images.py
    3. (Optional) Invalidate the token again afterwards

The script is resumable: already-downloaded images are skipped, so it can be re-run
after interruptions (network errors, rate limits) without re-downloading everything.

Images land in config.WC_CACHE_IMAGES_BASE as:
    article/<articleId>/<imageId>_<fileName>          (regular image)
    article/<articleId>/MAIN_<imageId>_<fileName>     (WeClapp main image)

The "MAIN_" prefix carries WeClapp's mainImage flag into the offline cache - the article
migration uses it to decide which file becomes the ERPNext item image (the rest become
plain attachments).
"""
import json
from pathlib import Path

import config
from weclapp import WeClappAPI


def download_article_images():
    articles = json.load(open(f"{config.WC_CACHE_BASE}article.json"))["data"]
    base = Path(config.WC_CACHE_IMAGES_BASE).joinpath("article")
    base.mkdir(parents=True, exist_ok=True)

    api = WeClappAPI(config.WC_API_TOKEN, config.WC_API_BASE)
    api.open()

    downloaded, skipped, failed = 0, 0, 0
    articles_with_images = [a for a in articles.values() if a.get("articleImages")]
    print(f"{len(articles_with_images)} articles with images "
          f"({sum(len(a['articleImages']) for a in articles_with_images)} images total)")

    for article in articles_with_images:
        article_dir = base.joinpath(article["id"])
        article_dir.mkdir(exist_ok=True)

        for image in article["articleImages"]:
            prefix = "MAIN_" if image.get("mainImage") else ""
            target = article_dir.joinpath(f"{prefix}{image['id']}_{image.get('fileName') or 'bild.jpg'}")
            if target.exists() and target.stat().st_size > 0:
                skipped += 1
                continue
            try:
                url = f"{config.WC_API_BASE}article/id/{article['id']}/downloadArticleImage"
                response = api._request(url, "GET", params={"articleImageId": image["id"]})
                target.write_bytes(response.content)
                downloaded += 1
                if downloaded % 100 == 0:
                    print(f"  ... {downloaded} downloaded")
            except Exception as e:
                failed += 1
                print(f"FAILED article {article.get('articleNumber')} image {image['id']}: {type(e).__name__}: {str(e)[:120]}")

    api.close()
    print(f"--- Article images: {downloaded} downloaded, {skipped} skipped (exists), {failed} failed ---")


if __name__ == "__main__":
    download_article_images()
