from web_backend.main import app
from mangum import Mangum

handler = Mangum(app)
