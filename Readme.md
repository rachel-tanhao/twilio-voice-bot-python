
How to deploy the code on Heroku:

heroku git:remote -a my-old-friend

heroku config:set DOMAIN=my-old-friend-fe65c61e6c2f.herokuapp.com

git add .
git commit -m "Updated code for deployment"

git push heroku main



How to run the project

python3 -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

uvicorn main:app --reload --host 0.0.0.0 --port 6060 --log-level debug