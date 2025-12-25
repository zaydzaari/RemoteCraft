import os
from dotenv import load_dotenv


load_dotenv()

class Config:
    def __init__(self):
        self.HOST = os.getenv('SERVER_HOST')
        self.USERNAME = os.getenv('SERVER_USER')  
        self.PASSWORD = os.getenv('SERVER_PASSWORD')    
        self.SERVER_PATH = os.getenv('SERVER_PATH')
        self.RAM = os.getenv('SERVER_RAM')
        if not self.HOST:
            raise ValueError("SERVER_HOST is required in .env file!")
        if not self.USERNAME:
            raise ValueError("SERVER_USER is required in .env file!")
        if not self.PASSWORD:
            raise ValueError("SERVER_PASSWORD is required in .env file!")
        if not self.SERVER_PATH:
            raise ValueError("SERVER_PATH is required in .env file!")
        if not self.RAM:
            raise ValueError("SERVER_RAM is required in .env file!")