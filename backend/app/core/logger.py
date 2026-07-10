from logger import logger

logger.add(

    "logs/app.log",

    rotation="10 MB",

    retention="30 days"

)