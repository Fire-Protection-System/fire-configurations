import logging
import logging.handlers
import os

def setup_logging(service_name):
    log_dir = os.environ.get('LOG_DIR', f"./logs/{service_name}")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except PermissionError:
        log_dir = f"./logs/{service_name}"
        os.makedirs(log_dir, exist_ok=True)
    
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03dZ [%(levelname)s] %(name)s - %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S'
    )
    
    log_file = os.path.join(log_dir, "application.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=1024*1024*1024,  
        backupCount=30
    )
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    logging.root.setLevel(logging.INFO)
    logging.root.addHandler(file_handler)
    logging.root.addHandler(console_handler)
    
    return logging.getLogger(service_name)