from fastapi import FastAPI, HTTPException, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
import httpx
import json
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
from prometheus_client import Counter, Histogram, generate_latest
from sqlalchemy import create_engine, Column, Integer, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="DevOps Metrics Backend")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration
DATABASE_URL = "postgresql://postgres:password@timescaledb:5432/metrics"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Kafka producer initialization
producer = None
max_retries = 5
retry_interval = 5  # seconds

def get_kafka_producer():
    global producer
    if producer is None:
        retries = 0
        while retries < max_retries:
            try:
                producer = KafkaProducer(
                    bootstrap_servers=['kafka:29092'],
                    value_serializer=lambda v: json.dumps(v).encode('utf-8')
                )
                logger.info("Successfully connected to Kafka")
                break
            except NoBrokersAvailable:
                retries += 1
                logger.warning(f"Failed to connect to Kafka. Retry {retries}/{max_retries}")
                if retries < max_retries:
                    time.sleep(retry_interval)
                else:
                    logger.error("Failed to connect to Kafka after maximum retries")
    return producer

# Prometheus metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests')
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency')

# Models
class SystemMetrics(Base):
    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    cpu_usage = Column(Float)
    memory_usage = Column(Float)
    network_latency = Column(Float)
    error_rate = Column(Float)

class MetricsData(BaseModel):
    cpu_usage: float
    memory_usage: float
    network_latency: float
    error_rate: float
    timestamp: Optional[int] = None

class PredictionResult(BaseModel):
    probability: float
    predicted_time: int
    confidence: float

# Create database tables
Base.metadata.create_all(bind=engine)

# Helper functions
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def send_to_ml_service(metrics: MetricsData) -> PredictionResult:
    try:
        # Ensure timestamp is set
        if metrics.timestamp is None:
            metrics.timestamp = int(datetime.utcnow().timestamp())

        async with httpx.AsyncClient() as client:
            logger.info(f"Sending metrics to ML service: {metrics.dict()}")
            response = await client.post(
                "http://ml_service:8000/predict",
                json=metrics.dict()
            )
            if response.status_code == 200:
                return PredictionResult(**response.json())
            logger.error(f"ML service error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=500, detail=f"ML service prediction failed: {response.text}")
    except Exception as e:
        logger.error(f"Error in send_to_ml_service: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def send_to_kafka(metrics: MetricsData):
    try:
        kafka_producer = get_kafka_producer()
        if kafka_producer:
            kafka_producer.send('metrics', value=metrics.dict())
            kafka_producer.flush()
        else:
            logger.error("Kafka producer not available")
    except Exception as e:
        logger.error(f"Error sending to Kafka: {e}")

# API endpoints
@app.post("/metrics", response_model=PredictionResult)
async def collect_metrics(metrics: MetricsData, background_tasks: BackgroundTasks):
    REQUEST_COUNT.inc()
    
    try:
        # Add timestamp if not provided
        if metrics.timestamp is None:
            metrics.timestamp = int(datetime.utcnow().timestamp())

        # Store metrics in TimescaleDB
        db = next(get_db())
        db_metrics = SystemMetrics(
            timestamp=datetime.fromtimestamp(metrics.timestamp),
            **{k: v for k, v in metrics.dict().items() if k != 'timestamp'}
        )
        db.add(db_metrics)
        db.commit()

        # Send metrics to Kafka in background
        background_tasks.add_task(send_to_kafka, metrics)

        # Get prediction from ML service
        prediction = await send_to_ml_service(metrics)
        
        return prediction

    except Exception as e:
        logger.error(f"Error processing metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/prometheus", response_class=Response)
def get_prometheus_metrics():
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )

@app.get("/health")
def health_check():
    # Try to connect to Kafka
    kafka_status = "healthy" if get_kafka_producer() else "unhealthy"
    
    # Check database connection
    try:
        db = next(get_db())
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    return {
        "status": "healthy",
        "kafka": kafka_status,
        "database": db_status
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)