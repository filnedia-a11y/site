import os

workers = 2                          # 2 workers (экономим RAM)
worker_class = 'gevent'              # Асинхронные workers
worker_connections = 100             # 100 подключений на worker = 200 всего!
timeout = 120
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
accesslog = '-'
errorlog = '-'
loglevel = 'info'
bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
preload_app = True
