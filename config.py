import os
piazza_email = os.environ['PIAZZA_EMAIL']
piazza_password = os.environ['PIAZZA_PASSWORD']
piazza_class_id = os.environ['PIAZZA_CLASS_ID']

slack_hook_url = os.environ['SLACK_HOOK_URL']
redis_cloud_url = os.environ['REDISCLOUD_URL']

pg_database_url = os.environ['DATABASE_URL']

sleep_duration = int(os.environ['SLEEP_DURATION'], 10)
