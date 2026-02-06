from dotenv import load_dotenv
load_dotenv(override=True)

import logging
import sys

# Configure logging to ensure output to stdout
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logging.getLogger('werkzeug').setLevel(logging.INFO)

from app import create_app
from app.utils.keep_alive import start_keep_alive
import os

# Create the Flask application instance
app = create_app(os.environ.get('FLASK_ENV', 'development'))

# Start keep-alive thread
start_keep_alive()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    is_development = os.environ.get('FLASK_ENV', 'development') == 'development'
    
    print(f" CBT Exam System Backend")
    print(f" Running on port {port}")
    print(f" Environment: {'Development' if is_development else 'Production'}")
    print(f" Environment: {'Development' if is_development else 'Production'}")
    print(f" MongoDB: {os.environ.get('MONGO_DBNAME', 'cbt_exam_database')}")
    print(f" CORS Origins: {app.config.get('CORS_ORIGINS')}")
    

    
    app.run(debug=is_development, host='0.0.0.0', port=port)
