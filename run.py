from dotenv import load_dotenv
load_dotenv(override=True)

from app import create_app
import os

# Create the Flask application instance
app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    is_development = os.environ.get('FLASK_ENV', 'development') == 'development'
    
    print(f" CBT Exam System Backend")
    print(f" Running on port {port}")
    print(f" Environment: {'Development' if is_development else 'Production'}")
    print(f" MongoDB: {os.environ.get('MONGO_DBNAME', 'cbt_exam_database')}")
    
    app.run(debug=is_development, host='0.0.0.0', port=port)
