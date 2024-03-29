import os

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
import numpy as np
import librosa  # for audio processing
import glob  # to retrieve files/pathnames matching a specified pattern
import matplotlib.pyplot as plt


class AudioDataset(Dataset):
    """
    Dataset class to be used in a PyTorch DataLoader to create batches.
    """
    def __init__(self, X, y):
        """
        This function initializes the dataset with the features and labels.

        Args:
            X (np.array): The features.
            y (np.array): The labels.
        """
        self.X = X
        self.y = y
        self.label_map = {"parkinson": 0, "notParkinson": 1}

    def __len__(self):
        """
        This function returns the size of the dataset.

        Returns:
            int: The size of the dataset.
        """
        return len(self.X)

    def __getitem__(self, idx):
        """
        This function returns a sample from the dataset at the specified index.

        Args:
            idx (int): The index of the sample.
        """
        # Convert labels to numerical values and then to tensor
        labels = torch.tensor(self.label_map[self.y[idx]])
        return self.X[idx], labels


def load_data():
    """
    This function loads the audio data and extracts the features using librosa.

    Returns:
        tuple: The features and labels for training, testing and validation sets.
    """
    # Define the directories for each category in train, test and validation sets
    categories = ['elderlyHealthyControl', 'peopleWithParkinson', 'youngHealthyControl']
    sets = ['train', 'test', 'validation']
    data = {set_name: {category: f'dataset2/{set_name}/{category}' for category in categories} for set_name in sets}

    # Initialize the features and labels for each set
    X_train, y_train, X_test, y_test, X_val, y_val = [], [], [], [], [], []

    for set_name, set_data in data.items():
        for category, dir in set_data.items():
            # Get all subfolders in the specified directory
            subfolders = [f.path for f in os.scandir(dir) if f.is_dir()]

            for subfolder in subfolders:
                # Get all .wav files in the subfolder
                audio_files = glob.glob(subfolder + '/trimmed/*.wav')

                for file in audio_files:
                    # Extract features using librosa
                    audio, sample_rate = librosa.load(file, res_type='kaiser_fast')  # resample to 22050 Hz
                    mfccs = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=40)  # extract 40 MFCCs
                    mfccs_processed = np.mean(mfccs.T, axis=0)  # average the MFCCs across all the frames

                    # Add the features to the appropriate list
                    label = "parkinson" if category == "peopleWithParkinson" else "notParkinson"
                    if set_name == 'train':
                        X_train.append(mfccs_processed)
                        y_train.append(label)
                    elif set_name == 'test':
                        X_test.append(mfccs_processed)
                        y_test.append(label)
                    else:  # validation set
                        X_val.append(mfccs_processed)
                        y_val.append(label)

    return np.array(X_train), np.array(y_train), np.array(X_test), np.array(y_test), np.array(X_val), np.array(y_val)


# Define the model
class AudioClassifier(nn.Module):
    def __init__(self):
        super(AudioClassifier, self).__init__()
        self.lstm = nn.LSTM(input_size=40, hidden_size=128, num_layers=2, dropout=0.5, batch_first=True)
        self.hidden_layer = nn.Linear(128, 64)
        self.relu = nn.ReLU()
        self.output_layer = nn.Linear(64, 2)

    def forward(self, x):
        x = x.unsqueeze(1)
        out, _ = self.lstm(x)
        out = out.view(out.shape[0], -1)
        out = self.hidden_layer(out)
        out = self.relu(out)
        out = self.output_layer(out)
        out = torch.softmax(out, dim=1)
        return out


def train_and_evaluate_model():
    X_train, y_train, X_test, y_test, X_val, y_val = load_data()

    # Create DataLoaders
    train_data = AudioDataset(X_train, y_train)
    test_data = AudioDataset(X_test, y_test)
    val_data = AudioDataset(X_val, y_val)

    train_loader = DataLoader(train_data, batch_size=32, shuffle=False)
    test_loader = DataLoader(test_data, batch_size=32, shuffle=True)
    val_loader = DataLoader(val_data, batch_size=32, shuffle=True)

    model = AudioClassifier()

    # Define loss and optimizer
    criterion = nn.CrossEntropyLoss()
    # optimizer = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.9)  # Using SGD with learning rate 0.01 and momentum 0.9
    # optimizer = torch.optim.Adam(model.parameters(), lr=0.00005, weight_decay=0.1)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.000009)

    model.train()
    n = 35
    # Initialize lists to store loss values
    train_losses = []
    val_losses = []

    # Training loop
    for epoch in range(n):  # Increase the number of epochs
        loss = None
        for i, (inputs, labels) in enumerate(train_loader):
            outputs = model(inputs.float())
            labels = labels.long()
            loss = criterion(outputs, labels)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        # Calculate validation loss
        val_loss = 0
        model.eval()
        with torch.no_grad():
            for inputs, labels in val_loader:
                outputs = model(inputs.float())
                labels = labels.long()
                loss = criterion(outputs, labels)
                val_loss += loss.item()
        val_loss /= len(val_loader)

        # Store loss values
        train_losses.append(loss.item())
        val_losses.append(val_loss)

        print(f'Epoch {epoch + 1}/{n} Train Loss: {loss.item()} Val Loss: {val_loss}')

    # Save the model
    torch.save(model.state_dict(), 'audio_classifier2.pth')

    model.eval()

    # Evaluation
    correct = 0
    total = 0

    with torch.no_grad():
        for inputs, labels in test_loader:
            outputs = model(inputs.float())
            _, predicted = torch.max(outputs.data, 1)
            total = total + labels.size(0)
            correct = correct + torch.sum(predicted.eq(labels)).item()

    print(f'Accuracy: {100 * correct / total}%')

    # Plot loss values
    plt.figure(figsize=(10, 5))
    plt.plot(train_losses, label='Training Loss')
    plt.plot(val_losses, label='Validation Loss')
    plt.xlabel('Epochs')
    plt.ylabel('Loss')
    plt.legend()
    plt.show()


def predict_audio(file_path, model):
    """
    This function predicts the class of an audio file using the trained model.

    Args:
        file_path (str): The path to the audio file that needs to be classified.
        model (AudioClassifier): The trained model.
    """
    # Load the audio file
    audio, sample_rate = librosa.load(file_path, res_type='kaiser_fast')

    # Extract MFCCs
    mfccs = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=40)
    mfccs_processed = np.mean(mfccs.T, axis=0)

    # Convert the MFCCs to PyTorch tensor
    mfccs_tensor = torch.tensor(mfccs_processed).float().unsqueeze(0)

    # Pass the tensor through the model
    output = model(mfccs_tensor)

    # Get the predicted class
    _, predicted = torch.max(output.data, 1)

    # Interpret the prediction
    """
    if predicted.item() == 0:
        return "Young Healthy"
    else:
        if predicted.item() == 1:
            return "Elderly Healthy"
        else:
            if predicted.item() == 2:
                return "Parkinson's"
    """

    if predicted.item() == 0:
        return "Parkinson's"
    else:
        return "Not Parkinson's"