Workflow
===

1. forward for local test

Browser smee.io and create a channel, then

```shell
pysmee forward https://smee.io/LgDQ8xrhy0q2GeET http://localhost:5000/events
```

2. Create github app with some permissions

filling following:

- GitHub App name
- Homepage URL
- Webhook URL
- Webhook secret

select permissions:

- Repository permissions
  - Checks: Read & write
  - Contents: Read & write
  - Pull requests: Read & write
- Subscribe to events
  - check suite
  - check run

after created

a. generate Private keys and get key file
    - checkruntestapp.2020-11-28.private-key.pem
b. get app id

3. install app to repository

select repository

4. run server 

```shell
python main.py
```
