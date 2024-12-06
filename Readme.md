
How to deploy the code on Heroku:

heroku git:remote -a my-old-friend

heroku config:set DOMAIN=my-old-friend-fe65c61e6c2f.herokuapp.com

git add .
git commit -m "Updated code for deployment"

git push heroku main