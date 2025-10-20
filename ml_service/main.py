from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
import torch
import torch.nn as nn
import numpy as np
from typing import List, Dict
from kafka import KafkaConsumer
import json
import threading
import logging
from prometheus_client import Counter, Histogram, generate_latest

# Prometheus metrics
PREDICTION_COUNT = Counter('prediction_requests_total', 'Total prediction requests')
PREDICTION_LATENCY = Histogram('prediction_duration_seconds', 'Prediction latency')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DevOps Downtime Prediction Service")

# Define data models
class MetricsData(BaseModel):
    cpu_usage: float
    memory_usage: float
    network_latency: float
    error_rate: float
    timestamp: int

class PredictionResponse(BaseModel):
    probability: float
    predicted_time: int
    confidence: float

# LSTM Model Definition
class DowntimePredictionModel(nn.Module):
    def __init__(self, input_size=4, hidden_size=64, num_layers=2):
        super(DowntimePredictionModel, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        # Reshape input to (batch_size, sequence_length, input_size)
        if len(x.shape) == 2:
            x = x.unsqueeze(1)  # Add sequence dimension
        
        # Initialize hidden state and cell state
        batch_size = x.size(0)
        h0 = torch.zeros(self.num_layers, batch_size, self.hidden_size)
        c0 = torch.zeros(self.num_layers, batch_size, self.hidden_size)
        
        # Forward propagate LSTM
        out, _ = self.lstm(x, (h0, c0))
        
        # Decode the hidden state of the last time step
        out = self.fc(out[:, -1, :])
        return out

# Initialize model
model = DowntimePredictionModel()
model.eval()

# Kafka consumer setup
def start_kafka_consumer():
    try:
        consumer = KafkaConsumer(
            'metrics',
            bootstrap_servers=['kafka:29092'],
            auto_offset_reset='latest',
            enable_auto_commit=True,
            group_id='ml_service_group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        for message in consumer:
            try:
                process_metrics(message.value)
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    except Exception as e:
        logger.error(f"Error in Kafka consumer: {e}")

def process_metrics(metrics_data: Dict):
    # Process incoming metrics and update model if needed
    logger.info(f"Processing metrics: {metrics_data}")
    # Add your metric processing logic here

# Start Kafka consumer in background
@app.on_event("startup")
async def startup_event():
    thread = threading.Thread(target=start_kafka_consumer, daemon=True)
    thread.start()

# API endpoints
@app.post("/predict", response_model=PredictionResponse)
async def predict_downtime(data: MetricsData):
    try:
        # Prepare input data
        input_data = torch.tensor([
            [
                data.cpu_usage,
                data.memory_usage,
                data.network_latency,
                data.error_rate
            ]
        ], dtype=torch.float32)
        
        # Make prediction
        with torch.no_grad():
            prediction = model(input_data)
        
        probability = float(prediction[0][0])
        
        # Calculate confidence based on historical accuracy
        confidence = 0.85  # Placeholder - should be calculated based on model performance
        
        # Predict time until potential downtime
        predicted_time = int(data.timestamp + (3600 if probability < 0.5 else 1800))
        
        return PredictionResponse(
            probability=probability,
            predicted_time=predicted_time,
            confidence=confidence
        )
    
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics", response_class=Response)
def metrics():
    return Response(content=generate_latest(), media_type="text/plain")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)