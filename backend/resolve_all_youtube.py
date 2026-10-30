"""One-time helper: convert every recipe's YouTube URL into a direct watch URL."""
from app import db_query, resolve_youtube_video


def main():
    rows = db_query('SELECT id, name, video_url FROM recipes ORDER BY id')
    total = len(rows)
    print(f'Resolving direct YouTube videos for {total} recipes...')

    resolved = 0
    failed = 0

    for i, row in enumerate(rows, 1):
        url, video_id = resolve_youtube_video(row['name'], row.get('video_url') or '')
        if url and video_id:
            db_query(
                'UPDATE recipes SET video_url=%s WHERE id=%s',
                (url, row['id']),
                fetch=False,
            )
            resolved += 1
            print(f'[{i}/{total}] OK   {row["name"]} -> {url}')
        else:
            failed += 1
            print(f'[{i}/{total}] FAIL {row["name"]}')

    print(f'Finished. Resolved: {resolved}, Failed: {failed}')


if __name__ == '__main__':
    main()
