FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy app code
COPY app /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8000

# Use uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]