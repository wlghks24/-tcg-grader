from pathlib import Path

path=Path('tcg_updater.py')
text=path.read_text(encoding='utf-8')
old='''        try:
            self.send_response(200)
            self.send_header('Content-type',self.guess_type(str(target)))
            self.send_header('Content-Length',str(metadata.st_size))
            self.send_header('Last-Modified',self.date_time_string(metadata.st_mtime))
            if target.suffix.lower() in {'.html','.js','.css','.json','.webmanifest'}:
                self.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Pragma','no-cache')
                self.send_header('Expires','0')
            else:
                self.send_header('Cache-Control','public, max-age=3600')
            self.end_headers()
            return handle
        except BaseException:
            handle.close()
            raise
'''
new='''        try:
            etag=f'"{metadata.st_mtime_ns:x}-{metadata.st_size:x}"'
            revalidate=target.suffix.lower() in {'.html','.js','.css','.json','.webmanifest'}
            cache_control=('private, no-cache, must-revalidate, max-age=0' if revalidate
                           else 'public, max-age=3600')
            if self.headers.get('If-None-Match','').strip()==etag:
                self.send_response(304)
                self.send_header('ETag',etag)
                self.send_header('Last-Modified',self.date_time_string(metadata.st_mtime))
                self.send_header('Cache-Control',cache_control)
                self.end_headers()
                handle.close()
                return None
            self.send_response(200)
            self.send_header('Content-type',self.guess_type(str(target)))
            self.send_header('Content-Length',str(metadata.st_size))
            self.send_header('Last-Modified',self.date_time_string(metadata.st_mtime))
            self.send_header('ETag',etag)
            self.send_header('Cache-Control',cache_control)
            self.end_headers()
            return handle
        except BaseException:
            handle.close()
            raise
'''
if text.count(old)!=1:
    raise SystemExit(f'send_head cache anchor mismatch: {text.count(old)}')
path.write_text(text.replace(old,new,1),encoding='utf-8')
