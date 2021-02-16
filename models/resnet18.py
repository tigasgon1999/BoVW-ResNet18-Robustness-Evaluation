from __future__ import print_function
from __future__ import division

import torch
import torch.nn as nn
import torch.optim as optim 
import numpy as np 
import pandas as pd
import torchvision
from torchvision import datasets, models, transforms
import matplotlib.pyplot as plt 
import time 
import os 
import copy 
from tqdm import tqdm

def train_model(model, dataloaders, criterion, optimizer, device, num_epochs=25, is_inception=False):
    since = time.time()

    train_acc_history = []
    train_loss_history = []

    val_acc_history = []
    val_loss_history = []

    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0
    
    for epoch in tqdm(range(num_epochs)):
        print('Epoch {}/{}'.format(epoch, num_epochs -1))
        print('-'*10)

        # Each epoch has a training and validation pass
        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()       # Set model to training mode
            else:
                model.eval()        # Set model to evaluate mode
            
            running_loss = 0.0
            running_corrects = 0

            # Iterate over data.
            print("Starting training ...")
            for inputs, labels in tqdm(dataloaders[phase]):
                inputs = inputs.to(device)
                labels = labels.to(device)

                # zero the parameter gradients
                optimizer.zero_grad()

                # forward
                # track history if only in train
                with torch.set_grad_enabled(phase == 'train'):
                    # Get model outputs and calculate loss
                    # Special case for incpetion beacuse in training it has an auziliary output.
                    # In train mode we calculate the loss by summing the final output and auxiliary output
                    # but in testing we only consider the final output.
                    if is_inception and phase == 'train':
                        outputs, aux_outputs = model(inputs)
                        loss1 = criterion(outputs, labels)
                        loss2 = criterion(aux_outputs, labels)
                        loss = loss1 + 0.4*loss2
                    else:
                        outputs = model(inputs)
                        loss = criterion(outputs, labels)

                    _, preds = torch.max(outputs, 1)

                    # Backpropagation + optimize only if in training phase
                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                # statistics
                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

            epoch_loss = running_loss / len(dataloaders[phase].dataset)
            epoch_acc = running_corrects.double() / len(dataloaders[phase].dataset)

            print('{} Loss: {:.4f} Acc: {:.4f}'.format(phase, epoch_loss, epoch_acc))

            # deep copy the model
            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())
            if phase == 'val':
                val_acc_history.append(epoch_acc.numpy())
                val_loss_history.append(epoch_loss)
            else:
                train_acc_history.append(epoch_acc.numpy())
                train_loss_history.append(epoch_loss)

    time_elapsed = time.time() - since
    print('\nTraining complete in {:.0f}m {:.0f}s'.format(time_elapsed // 60, time_elapsed % 60))
    print('Best val Acc: {:4f}'.format(best_acc))

    # load best model weights
    model.load_state_dict(best_model_wts)

    return model, val_acc_history, val_loss_history, train_acc_history, train_loss_history, best_acc.numpy(), time_elapsed

def set_parameter_requires_grad(model, feature_extracting):
    if feature_extracting:
        for param in model.parameters():
            param.requires_grad = False

def initialize_model(model_name, num_classes, feature_extract, use_pretrained=True):
    # Initialize these variables which will be set in this if statement.
    # Each of these variables is model specific.
    model_ft = None
    input_size = 0

    if model_name == "resnet":
        '''
        Resnet18
        '''
        model_ft = models.resnet18(pretrained = use_pretrained)
        set_parameter_requires_grad(model_ft, feature_extract)
        num_ftrs = model_ft.fc.in_features
        model_ft.fc = nn.Linear(num_ftrs, num_classes)
        input_size = 224

    else:
        print("Invalid model name, exiting...")
        exit()

    return model_ft, input_size

def get_K_fold_data(data_dir, bs):
    # Data augmentation and normalization for training
    # Just normalization for validation
    data_transforms = {
        'train': transforms.Compose([
            transforms.RandomResizedCrop(input_size),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ]),
        'val': transforms.Compose([
            transforms.Resize(input_size),
            transforms.CenterCrop(input_size),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ]),
    }

    # Create training and validation datasets
    dataloaders_dict = {}
    for split in range(1,4):
        split_dir = data_dir+'/split_'+str(split) 
        image_datasets = {x: datasets.ImageFolder(os.path.join(split_dir, x), data_transforms[x]) for x in ['train', 'val']}

        # Create training and validation dataloaders
        dataloaders_dict[str(split)] = {x: torch.utils.data.DataLoader(image_datasets[x], batch_size=bs, shuffle=True, num_workers=4) for x in ['train', 'val']}

    return dataloaders_dict


#----------------------------------------------------------------------------------------------
#                                       MAIN FUNCTION                                             
#----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    # Top level data directory. Here we assume the format of the directory conforms to the ImageFolder structure
    # Models to choose from [resnet, alexnet, vgg, squeezenet, densenet, inception]
    data_dir = "./data"
    model_name = "resnet"
    num_classes = 2
    batch_size = 50
    num_epochs = 1
    # Flag for feature extracting. When False, we finetune the whole model,
    # when True we only update the reshaped layer params
    feature_extract = True

    # Initialize the model for this run
    model_ft, input_size = initialize_model(model_name, num_classes, feature_extract, use_pretrained=True)

    print("Initializing Datasets and Dataloaders...")
    # Get cross-validation data
    data_loaders_dict = get_K_fold_data(data_dir, bs= batch_size)
    
    # Detect if we have a GPU available
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    # Send the model to GPU
    model_ft = model_ft.to(device)

    # Initialize optimizer
    params_to_update = model_ft.parameters()

    if feature_extract:
        params_to_update = []
        for name, param in model_ft.named_parameters():
            if param.requires_grad == True:
                params_to_update.append(param)

    else:
        for name, param in model_ft.named_parameters():
            if param.requires_grad == True:
                pass

    # Define optimizer
    optimizer_ft = optim.SGD(params_to_update, lr=0.01, momentum=0.9)

    # Setup the loss function
    criterion =  nn.CrossEntropyLoss()

    # Train 3 full models
    # Define variables to store values
    training_output = {}

    for loader in data_loaders_dict:
        print(f"\n ## On split No. {loader} ##\n")
        # Train model
        model_ft, val_acc_history, val_loss_history, train_acc_history, train_loss_history, best_acc, time_elapsed = train_model(
            model_ft, data_loaders_dict[loader], criterion, optimizer_ft, device, num_epochs=num_epochs, is_inception=(model_name=="inception"))
        
        # Record data
        training_output['train_loss'] = train_loss_history
        training_output['train_acc'] = train_acc_history
        training_output['val_loss'] = val_loss_history
        training_output['val_acc'] = val_acc_history
        training_output['best_acc'] = [best_acc]*num_epochs
        training_output['runtime(s)'] = [time_elapsed]*num_epochs
        
        # Output data
        root_output_dir = "./output/progress/"
        df_name = root_output_dir+"split_"+loader+".csv"
        print(f"Outputting data to {df_name}...")
        pd.DataFrame.from_dict(training_output).to_csv(df_name, index=False)
        torch.save(model_ft.state_dict(), './output/weights/split_'+loader+'.pth')
        print(f"Saving final trained model to ")
        # Reset recorder
        training_output = {}