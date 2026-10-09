"""One loopback web process only; no collection worker or migration."""
bind = '127.0.0.1:8003'
workers = 1
worker_class = 'sync'
threads = 1
timeout = 120
reload = False
daemon = False
accesslog = None
errorlog = '-'
loglevel = 'warning'
forwarded_allow_ips = '127.0.0.1,::1'
secure_scheme_headers = {'X-FORWARDED-PROTO': 'https'}
