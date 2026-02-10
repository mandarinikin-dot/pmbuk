from flask import Flask, render_template, jsonify
from bs4 import BeautifulSoup
from flask_cors import CORS
import re
import cloudscraper

app = Flask(__name__)
CORS(app)

video_cache = {'data': [], 'timestamp': 0}
CACHE_DURATION = 300

TARGET_SITE = "https://www.xv-ru.com/?k=sissy"

def parse_main_page():
    """Парсинг главной страницы"""
    try:
        print("="*60)
        print(f"Запрос к {TARGET_SITE}")

        scraper = cloudscraper.create_scraper()
        response = scraper.get(TARGET_SITE, timeout=15)

        print(f"Статус: {response.status_code}")

        soup = BeautifulSoup(response.content, 'html.parser')
        videos = []

        # Ищем все видео блоки
        video_blocks = soup.find_all('div', class_='thumb-block')
        print(f"✓ Найдено {len(video_blocks)} видео блоков")

        for block in video_blocks:
            try:
                # Ссылка на видео
                link = block.find('a', href=re.compile(r'/video'))
                if not link:
                    continue

                href = link.get('href', '')

                # ID из URL
                video_id_match = re.search(r'/video\.([a-z0-9]+)/', href)
                if not video_id_match:
                    continue

                video_id = video_id_match.group(1)

                # НАЗВАНИЕ из title атрибута ссылки в thumb-under
                title_link = block.find('p', class_='title')
                if title_link:
                    title_a = title_link.find('a')
                    if title_a:
                        # Берем title атрибут
                        title = title_a.get('title', '')
                        # Убираем длительность из title если есть
                        title = re.sub(r'\s*<span class="duration">.*?</span>\s*$', '', title)

                # Если title не найден, пробуем текст
                if not title:
                    if title_a:
                        title_text = title_a.get_text(strip=True)
                        # Убираем длительность из конца
                        title = re.sub(r'\s+\d+\s+(мин\.|сек\.|ч\.).*$', '', title_text)

                if not title:
                    title = f"Video {video_id}"

                # Полный URL
                video_url = TARGET_SITE.rstrip('/') + href if href.startswith('/') else href

                # Thumbnail
                thumbnail = ""
                img = block.find('img')
                if img:
                    thumbnail = (img.get('data-src') or
                                img.get('data-thumb_url') or
                                img.get('src') or "")

                    if thumbnail and thumbnail.startswith('//'):
                        thumbnail = 'https:' + thumbnail

                # Длительность
                duration = "00:00"
                dur_span = block.find('span', class_='duration')
                if dur_span:
                    duration = dur_span.get_text(strip=True)

                videos.append({
                    'id': video_id,
                    'title': title.strip(),
                    'page_url': video_url,
                    'thumbnail': thumbnail,
                    'duration': duration
                })

                print(f"✓ {video_id}: {title[:80]}")

            except Exception as e:
                print(f"⚠ Ошибка парсинга блока: {e}")
                continue

        print(f"ИТОГО: {len(videos)} видео")
        return videos

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_video_embed_url(video_id):
    """Получение iframe URL для встраивания"""
    embed_url = f"https://www.xv-ru.com/embedframe/{video_id}"
    print(f"✓ Embed URL: {embed_url}")

    return {
        'type': 'iframe',
        'url': embed_url
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/videos')
def get_videos():
    import time
    current_time = time.time()
    if current_time - video_cache['timestamp'] > CACHE_DURATION or not video_cache['data']:
        print("\n🔄 Обновление кеша...")
        video_cache['data'] = parse_main_page()
        video_cache['timestamp'] = current_time
    else:
        remaining = int(CACHE_DURATION - (current_time - video_cache['timestamp']))
        print(f"✓ Кеш ({remaining} сек, видео: {len(video_cache['data'])})")

    return jsonify(video_cache['data'])

@app.route('/api/video/<video_id>')
def get_video_details(video_id):
    videos = video_cache['data'] if video_cache['data'] else parse_main_page()
    video = next((v for v in videos if v['id'] == video_id), None)

    if video:
        embed_data = get_video_embed_url(video_id)
        video['embed'] = embed_data
        return jsonify(video)

    return jsonify({'error': 'Video not found'}), 404

@app.route('/api/refresh')
def refresh():
    video_cache['timestamp'] = 0
    videos = parse_main_page()

    # Добавляем embed для первых 3 видео
    for video in videos[:3]:
        video['embed'] = get_video_embed_url(video['id'])

    return jsonify({
        'total': len(videos),
        'videos': videos[:3]
    })

if __name__ == '__main__':
    print("="*60)
    print("🚀 http://localhost:5000")
    print("🔄 http://localhost:5000/api/refresh")
    print("="*60)
    app.run(debug=True, port=5000)
