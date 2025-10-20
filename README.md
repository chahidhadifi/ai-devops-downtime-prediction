# AI DevOps Downtime Prediction System

A proactive monitoring system that uses machine learning to predict potential infrastructure failures before they occur. The system collects various system metrics, processes them in real-time, and provides early warnings for possible downtimes.

## Architecture

- **Data Pipeline**: Kafka + Spark Streaming for real-time data processing
- **Machine Learning**: PyTorch LSTM model for time series prediction
- **Backend**: FastAPI for REST API endpoints
- **Storage**: TimescaleDB for time-series metrics data
- **Monitoring**: Prometheus + Grafana for system monitoring
- **Deployment**: Docker + Docker Compose

## Components

1. **ML Service** (Port 8000)
   - LSTM-based prediction model
   - Real-time metric processing
   - REST API endpoints for predictions

2. **Backend Service** (Port 8001)
   - Metrics collection and storage
   - Integration with ML service
   - Prometheus metrics exposure

3. **Data Infrastructure**
   - Kafka (Port 9092)
   - TimescaleDB (Port 5432)
   - Spark Master (Port 8080)

4. **Monitoring Stack**
   - Prometheus (Port 9090)
   - Grafana (Port 3000)

## Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ai-devops-downtime-prediction
   ```

2. Start the services:
   ```bash
   docker-compose up -d
   ```

3. Access the services:
   - ML Service API: http://localhost:8000
   - Backend API: http://localhost:8001
   - Grafana Dashboard: http://localhost:3000 (admin/admin)
   - Prometheus: http://localhost:9090

## API Endpoints

### Backend Service

- `POST /metrics`
  - Submit system metrics for prediction
  - Returns prediction results

- `GET /metrics/prometheus`
  - Prometheus metrics endpoint

- `GET /health`
  - Health check endpoint

### ML Service

- `POST /predict`
  - Get downtime predictions for given metrics

- `GET /health`
  - Health check endpoint

## Metrics Format

```json
{
    "cpu_usage": 75.5,
    "memory_usage": 82.3,
    "network_latency": 120.0,
    "error_rate": 0.05
}
```

## Development

1. Install dependencies for local development:
   ```bash
   cd ml_service
   pip install -r requirements.txt

   cd ../backend
   pip install -r requirements.txt
   ```

2. Run services individually:
   ```bash
   # ML Service
   cd ml_service
   uvicorn main:app --reload --port 8000

   # Backend Service
   cd backend
   uvicorn main:app --reload --port 8001
   ```

## Monitoring

1. Access Grafana at http://localhost:3000
2. Default credentials: admin/admin
3. Add Prometheus data source: http://prometheus:9090
4. Import dashboards for monitoring:
   - System metrics
   - ML model performance
   - Service health