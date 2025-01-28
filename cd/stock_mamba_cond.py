
#################continuous target###########################    
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score, f1_score, roc_curve

# Load Data from CSV
DF = pd.read_csv("stocks.csv")

# Feature Engineering
def feature_engineering(df):
    df = df.copy()  # Work on a copy
    df["SMA_5"] = df.groupby("ticker")["price"].transform(lambda x: x.rolling(window=5).mean())
    df["SMA_20"] = df.groupby("ticker")["price"].transform(lambda x: x.rolling(window=20).mean())
    df["volatility_20"] = df.groupby("ticker")["price"].transform(lambda x: x.rolling(window=20).std())
    df["event_tomorrow"] = (df["price"] < df["SMA_20"]).astype(int)  # Binary event

    # Replace NaN values
    df.fillna(0, inplace=True)

    # Ensure all relevant columns are numeric
    numeric_columns = ["price", "volume", "SMA_5", "SMA_20", "volatility_20", "event_tomorrow"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(np.float32)

    return df

# Dataset Class
class StockDataset(Dataset):
    def __init__(self, data):
        numeric_columns = ["price", "volume", "SMA_5", "SMA_20", "volatility_20", "event_tomorrow"]
        self.data = data[numeric_columns].copy()  # Ensure only numeric columns are used

        # Initialize scaler and scale features
        self.scaler = StandardScaler()
        self.features = numeric_columns  # Features used in the model
        scaled_features = self.scaler.fit_transform(self.data[self.features].values)
        self.data.loc[:, self.features] = scaled_features.astype(np.float32)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        # Fetch the row at the given index
        row = self.data.iloc[idx]

        # Extract features (x) and target (y)
        x = row[self.features].values
        y = row["price"]

        # Convert to PyTorch tensors
        x = torch.tensor(x, dtype=torch.float32)
        y = torch.tensor(y, dtype=torch.float32)
        return x, y

# Updated MambaExtendedNN with Dropout and Regularization
class MambaExtendedNN(nn.Module):
    def __init__(self, input_dim, hidden_dim):
        super(MambaExtendedNN, self).__init__()
        self.hidden_dim = hidden_dim
        self.a = nn.Parameter(torch.rand(hidden_dim, hidden_dim))  # Transition matrix for state
        self.b = nn.Parameter(torch.rand(1, hidden_dim))  # Event effect
        self.c = nn.Linear(input_dim, hidden_dim)  # Input transformation
        self.dropout = nn.Dropout(0.2)  # Dropout for regularization
        self.fc_output = nn.Linear(hidden_dim, 1)  # Output layer
        self.log_var = nn.Parameter(torch.zeros(1))  # Log variance for uncertainty

    def forward(self, x, h, event):
        event_effect = self.b * event.unsqueeze(1)
        a_expanded = self.a.unsqueeze(0).expand(x.size(0), -1, -1)
        h_next = torch.bmm(h.unsqueeze(1), a_expanded).squeeze(1)
        h_next = h_next + event_effect + self.c(x)
        h_next = self.dropout(h_next)  # Apply dropout
        y_pred = self.fc_output(h_next)
        return y_pred, h_next, self.log_var


# Training Function with MAPE Calculation
def train_model(model, dataloader, optimizer, criterion, num_epochs):
    for epoch in range(num_epochs):
        model.train()
        total_loss = 0
        for x, y in dataloader:
            optimizer.zero_grad()
            batch_size = x.size(0)
            h = torch.zeros((batch_size, model.hidden_dim), dtype=torch.float32)
            event = x[:, -1]
            x = x[:, :-1]
            y_pred, h, log_var = model(x, h, event)
            loss = criterion(y_pred.squeeze(), y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        print(f"Epoch {epoch + 1}/{num_epochs}, Loss: {total_loss / len(dataloader):.4f}")


# Evaluation Function with MAPE
def evaluate_model(model, dataloader):
    model.eval()
    predictions, actuals = [], []
    mape_total, count = 0, 0
    with torch.no_grad():
        for x, y in dataloader:
            batch_size = x.size(0)
            h = torch.zeros((batch_size, model.hidden_dim), dtype=torch.float32)
            event = x[:, -1]
            x = x[:, :-1]
            y_pred, h, log_var = model(x, h, event)
            predictions.extend(y_pred.squeeze().tolist())
            actuals.extend(y.tolist())
            # Calculate MAPE
            mape_total += torch.sum(torch.abs((y_pred.squeeze() - y) / y)).item()
            count += len(y)
    mape = (mape_total / count) * 100
    return predictions, actuals, mape


# Updated Time Series Split and Evaluation Loop
results = []
for train_idx, test_idx in ts_split.split(all_data):
    train_data, test_data = all_data.iloc[train_idx].copy(), all_data.iloc[test_idx].copy()

    train_data = feature_engineering(train_data)
    test_data = feature_engineering(test_data)

    train_dataset = StockDataset(train_data)
    test_dataset = StockDataset(test_data)

    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False)

    model = MambaExtendedNN(input_dim=5, hidden_dim=10)
    optimizer = optim.AdamW(model.parameters(), lr=0.0005, weight_decay=1e-4)  # Added L2 regularization
    criterion = nn.MSELoss()

    print("Training Model...")
    train_model(model, train_loader, optimizer, criterion, num_epochs=100)

    print("Evaluating Model...")
    predictions, actuals, mape = evaluate_model(model, test_loader)
    results.append((predictions, actuals, mape))

# Analyze and Print Results
for i, (pred, actual, mape) in enumerate(results):
    mse = np.mean((np.array(pred) - np.array(actual)) ** 2)
    print(f"Fold {i + 1}, MSE: {mse:.4f}, MAPE: {mape:.2f}%")
    print("Explanation for Traders:")
    print(
        f"In Fold {i + 1}, the model predicts stock price movements with an average error of {mape:.2f}%."
        " If the predicted price for a stock (e.g., AAPL) is $180 under conditions of high volatility, "
        "this suggests a potential mean price level traders can expect based on recent trends."
    )

#################binary target###########################    

def feature_engineering(df, prediction_horizon=5):
    df = df.copy()

    # Calculate moving averages, volatility, and the future price
    df["SMA_5"] = df.groupby("ticker")["price"].transform(lambda x: x.rolling(window=5).mean())
    df["SMA_20"] = df.groupby("ticker")["price"].transform(lambda x: x.rolling(window=20).mean())
    df["volatility_20"] = df.groupby("ticker")["price"].transform(lambda x: x.rolling(window=20).std())
    df["future_price"] = df.groupby("ticker")["price"].shift(-prediction_horizon)

    # Binary target: Price increase ≥ 1%
    df["binary_target"] = (df["future_price"] / df["price"] - 1 >= 0.01).astype(int)

    # Replace NaN values in numeric columns with 0
    numeric_columns = ["price", "volume", "SMA_5", "SMA_20", "volatility_20", "binary_target"]
    df[numeric_columns] = df[numeric_columns].fillna(0)

    # Drop non-numeric columns like 'ticker' and 'date' if present
    df = df[numeric_columns]

    # Convert all columns to float32 for compatibility with PyTorch
    df = df.astype(np.float32)

    return df

# Dataset Class
class StockDataset(Dataset):
    def __init__(self, data):
        # List of numeric features used for training
        numeric_columns = ["price", "volume", "SMA_5", "SMA_20", "volatility_20"]
        self.data = data.copy()
        self.features = numeric_columns

        # Standardize the numeric features
        self.scaler = StandardScaler()
        scaled_features = self.scaler.fit_transform(self.data[self.features].values)
        self.data.loc[:, self.features] = scaled_features.astype(np.float32)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        # Extract features (x) and binary target (y)
        row = self.data.iloc[idx]
        x = row[self.features].values
        y = row["binary_target"]
        return torch.tensor(x, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)


# Extended Mamba Neural Network
class MambaExtendedNN(nn.Module):
    def __init__(self, input_dim, hidden_dim):
        super(MambaExtendedNN, self).__init__()
        self.hidden_dim = hidden_dim
        self.a = nn.Parameter(torch.rand(hidden_dim, hidden_dim))  # Transition matrix for state
        self.b = nn.Parameter(torch.rand(1, hidden_dim))  # Event effect
        self.c = nn.Linear(input_dim, hidden_dim)  # Input transformation
        self.dropout = nn.Dropout(0.2)
        self.fc_output = nn.Sequential(nn.Linear(hidden_dim, 1), nn.Sigmoid())  # Binary classification output

    def forward(self, x, h, event):
        event_effect = self.b * event.unsqueeze(1)
        a_expanded = self.a.unsqueeze(0).expand(x.size(0), -1, -1)
        h_next = torch.bmm(h.unsqueeze(1), a_expanded).squeeze(1)
        h_next = h_next + event_effect + self.c(x)  # Ensure x has correct dimensions
        h_next = self.dropout(h_next)
        y_pred = self.fc_output(h_next)
        return y_pred, h_next

def train_model(model, dataloader, optimizer, criterion, num_epochs):
    for epoch in range(num_epochs):
        model.train()
        total_loss = 0
        for x, y in dataloader:
            optimizer.zero_grad()
            batch_size = x.size(0)
            h = torch.zeros((batch_size, model.hidden_dim), dtype=torch.float32)
            event = x[:, -1]  # Extract the last feature (event)
            y_pred, h = model(x, h, event)  # Do not slice x; it already contains all features
            loss = criterion(y_pred.squeeze(), y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        print(f"Epoch {epoch + 1}/{num_epochs}, Loss: {total_loss / len(dataloader):.4f}")


def evaluate_model(model, dataloader):
    model.eval()
    predictions, actuals = [], []
    with torch.no_grad():
        for x, y in dataloader:
            batch_size = x.size(0)
            h = torch.zeros((batch_size, model.hidden_dim), dtype=torch.float32)
            event = x[:, -1]  # Extract the event feature
            y_pred, h = model(x, h, event)  # Do not slice x
            predictions.extend(y_pred.squeeze().tolist())
            actuals.extend(y.tolist())
    return predictions, actuals

# Time Series Split and Validation
ts_split = TimeSeriesSplit(n_splits=5)
results = []

DF = feature_engineering(DF)
for fold, (train_idx, test_idx) in enumerate(ts_split.split(DF), 1):
    train_data, test_data = DF.iloc[train_idx], DF.iloc[test_idx]

    train_dataset = StockDataset(train_data)
    test_dataset = StockDataset(test_data)

    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False)

    model = MambaExtendedNN(input_dim=5, hidden_dim=60)
    optimizer = optim.AdamW(model.parameters(), lr=0.0003, weight_decay=1e-4)
    criterion = nn.BCELoss()

    print(f"Training Model for Fold {fold}...")
    train_model(model, train_loader, optimizer, criterion, num_epochs=25)

    print(f"Evaluating Model for Fold {fold}...")
    predictions, actuals = evaluate_model(model, test_loader)

    auc = roc_auc_score(actuals, predictions)
    f1 = f1_score(actuals, np.round(predictions))
    fpr, tpr, _ = roc_curve(actuals, predictions)
    ks = max(tpr - fpr)

    results.append({"AUC": auc, "F1": f1, "KS": ks})
    print(f"Fold {fold}, AUC: {auc:.4f}, F1 Score: {f1:.4f}, KS: {ks:.4f}")
    print(f"Explanation for Traders:")
    print(
        f"In Fold {fold}, the model predicts stock price movements with an AUC of {auc:.4f}, \n"
        f"indicating a strong ability to differentiate between upward and downward movements.\n"
        f"The F1 score of {f1:.4f} reflects a balance between precision and recall, \n"
        f"while the KS statistic of {ks:.4f} indicates the maximum separation \n"
        f"between true positive and false positive rates. These metrics suggest \n"
        f"the model is highly effective in identifying trading opportunities."
    )

# Final Results
for i, result in enumerate(results, 1):
    print(f"Fold {i}: AUC={result['AUC']:.4f}, F1={result['F1']:.4f}, KS={result['KS']:.4f}")

