https://docs.google.com/presentation/d/1kq9ytSBdUUAwsIar7FfbGgkLle2JOw-YiheypJMMFZ8/edit#slide=id.g31ab35e2b92_0_11



<img width="783" alt="image" src="https://github.com/user-attachments/assets/846b90ff-482d-48d9-8298-109ebd0f9fee" />

<img width="852" alt="image" src="https://github.com/user-attachments/assets/3dde9733-6321-4708-a2aa-27e1ac8c2fab" />

<img width="828" alt="image" src="https://github.com/user-attachments/assets/af4f1378-60a7-4580-b360-bb7229d1f0c3" />

<img width="808" alt="image" src="https://github.com/user-attachments/assets/2a8989d3-5b4f-4623-8d95-81756c0f3f5c" />

<img width="883" alt="image" src="https://github.com/user-attachments/assets/28a0525d-ee4b-4d7f-a4b7-4ea01b62ff57" />






How to deploy the code on Heroku:

heroku git:remote -a my-old-friend

heroku config:set DOMAIN=my-old-friend-fe65c61e6c2f.herokuapp.com

git add .
git commit -m "Updated code for deployment"

git push heroku main

heroku logs --tail



How to run the project

python3 -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

uvicorn main:app --reload --host 0.0.0.0 --port 6060 --log-level debug
