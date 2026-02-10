from flask import Flask, render_template, jsonify, request
from bs4 import BeautifulSoup
from flask_cors import CORS
import re
import cloudscraper

app = Flask(__name__)
CORS(app)

video_cache = {}
CACHE_DURATION = 300

TARGET_SITE = "https://www.xv-ru.com/?k=sissy&typef=gay"

def parse_main_page(page=0):
    """Парсинг главной страницы с поддержкой пагинации"""
    try:
        print("="*60)

        # Формируем URL с параметром страницы
        if page > 0:
            url = f"{TARGET_SITE}&p={page}"
        else:
            url = TARGET_SITE

        print(f"Запрос к {url}")

        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=15)

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
                title = ""
                if title_link:
                    title_a = title_link.find('a')
                    if title_a:
                        # Берем title атрибут
                        title = title_a.get('title', '')
                        # Убираем длительность из title если есть
                        title = re.sub(r'\s*<span class="duration">.*?</span>\s*$', '', title)

                # Если title не найден, пробуем текст
                if not title:
                    if title_link:
                        title_a = title_link.find('a')
                        if title_a:
                            title_text = title_a.get_text(strip=True)
                            # Убираем длительность из конца
                            title = re.sub(r'\s+\d+\s+(мин\.|сек\.|ч\.).*$', '', title_text)

                if not title:
                    title = f"Video {video_id}"

                # Полный URL
                video_url = TARGET_SITE.split('?')[0].rstrip('/') + href if href.startswith('/') else href

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

        print(f"ИТОГО: {len(videos)} видео на странице {page}")
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

    # Получаем номер страницы из параметров запроса
    page = request.args.get('page', 0, type=int)

    cache_key = f'page_{page}'
    current_time = time.time()

    # Проверяем кеш для конкретной страницы
    if cache_key not in video_cache:
        video_cache[cache_key] = {'data': [], 'timestamp': 0}

    if current_time - video_cache[cache_key]['timestamp'] > CACHE_DURATION or not video_cache[cache_key]['data']:
        print(f"\n🔄 Обновление кеша для страницы {page}...")
        video_cache[cache_key]['data'] = parse_main_page(page)
        video_cache[cache_key]['timestamp'] = current_time
    else:
        remaining = int(CACHE_DURATION - (current_time - video_cache[cache_key]['timestamp']))
        print(f"✓ Кеш страницы {page} ({remaining} сек, видео: {len(video_cache[cache_key]['data'])})")

    return jsonify({
        'videos': video_cache[cache_key]['data'],
        'page': page,
        'total': len(video_cache[cache_key]['data'])
    })

@app.route('/api/video/<video_id>')
def get_video_details(video_id):
    # Ищем видео в кеше всех страниц
    video = None
    for cache_key in video_cache:
        if video_cache[cache_key]['data']:
            video = next((v for v in video_cache[cache_key]['data'] if v['id'] == video_id), None)
            if video:
                break

    # Если не найдено в кеше, парсим первую страницу
    if not video:
        videos = parse_main_page(0)
        video = next((v for v in videos if v['id'] == video_id), None)

    if video:
        embed_data = get_video_embed_url(video_id)
        video['embed'] = embed_data
        return jsonify(video)

    return jsonify({'error': 'Video not found'}), 404

@app.route('/api/refresh')
def refresh():
    # Очищаем весь кеш
    video_cache.clear()
    videos = parse_main_page(0)

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
