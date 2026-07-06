Step 1: (Optional but recommended) Create a virtual environment
```
    python3 -m venv env
```
```
    source env/bin/activate
```
Step 2: Install Locust
```
    pip install locust
```

Step 3: Verify installation
```
    locust --version
```

Step 4: Run
```
    locust
```# kkl-locust


watch -n 1 "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'"

docker service scale <service_name>=6

docker service scale \
  ithq-kkl-app-services=8 \
  ithq-kkl-sell-services=8 \
  ithq-kkl-producer-service=6 \
  ithq-kkl-core=6

  docker service scale ithq-kkl-app-services=12




locust -f locustfile_balance.py

locust -f simulate.locustfile.py

# kkl-locust-load
