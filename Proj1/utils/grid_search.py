import torch 
import matplotlib.pyplot as plt
import sys
import numpy as np
import random
sys.path.append('..')
from torch import nn 
from torch.nn import functional as F
from torch import optim
import torch.utils.data as dt
from torch.utils.data import Dataset, DataLoader
from utils.loader import load,PairSetMNIST,Training_set,Test_set, Training_set_split,Validation_set
from utils.plot import learning_curve, boxplot
from utils.metrics import accuracy, compute_nb_errors, compute_metrics
from utils.training import train_model
import torch.cuda as cuda
from models.Inception_Net import Google_Net
from models.Basic import Net2C
from models.Le_Net import LeNet_sharing_aux,LeNet_sharing


def grid_search_basic(lrs,drop_prob, hidden_layers, seeds,  mini_batch_size=100, optimizer = optim.Adam,criterion = nn.CrossEntropyLoss(),
                      n_epochs=40, lambda_l2 = 0,alpha=0.5, beta=0.5, rotate = False,translate=False,swap_channel = False, GPU=False):
    
    """
    
     General : Iterate over combinations of parameters list to optimize and repeat a 10 round training/validation procedure at each
               combination -> Select the combination with the highest validation accuracy for a Net2c network
               
               => only called in the <Nets> class by the Tune_Net2c function
               
     Input : 
         
         - lrs : list of learning rate
         - drop_prob : list of dropout rate
         - hidden_layers : list of  number of nodes in the hidden layer 
         - seeds : list of seeds for statistics 
         -> mini_batch_size,optimizer, criterion, n_epochs, eta, lambda_2, alpha, beta see training.py
         -> rotate,translate and swap_channels -> data augmentation see loader.py 
        
     Ouput :
         
         - train_results : A (len(lrs)xlen(drop_prob)xlen(hidden_layers)xlen(seeds),4,n_epochs) tensor
                           len() -> number of parameters or seed
                           4 -> train loss ,train accuracy, validation loss, validation accuracy
                           n_epochs -> evolution during training
         - test_losses : A tensor of shape (10,) containing the test loss at each seed
         - test_accuracies : A tensor of shape (10,) containing the test loss at each seed
         - opt_lr : tuned value for learning rate 
         - opt_prob : tuned value for drop_prob
         - opt_hidden_layer : tuned value for hidden_layers
    """
    # tensor to record the metrics
    train_results = torch.empty(len(lrs),len(drop_prob),len(hidden_layers),len(seeds), 4, n_epochs)
    test_losses = torch.empty(len(lrs),len(drop_prob), len(hidden_layers), len(seeds))
    test_accuracies = torch.empty(len(lrs),len (drop_prob), len(hidden_layers), len(seeds))
    
    # iterate over the parameter combiantion for each seed in seeds
    for idz,eta in enumerate(lrs) :
        for idx,prob in enumerate(drop_prob):
            for idy,nb_hidden in enumerate(hidden_layers) :
                for n, seed in enumerate(seeds):
                    print('lr : {:.4f} , prob : {:.2f}, nb_hidden : {:d} (n= {:d})'.format(eta,prob, nb_hidden, n))

                    # set the pytorch seeds
                    torch.manual_seed(seed)
                    torch.cuda.manual_seed(seed)
                    
                    #set the random seed 
                    random.seed(0)

                    # create the dataset 
                    data = PairSetMNIST()
                    train_data = Training_set(data)
                    test_data = Test_set(data)
                    train_data_split =Training_set_split(train_data,rotate,translate,swap_channel)
                    validation_data= Validation_set(train_data)

                    # create the network
                    model = Net2C(nb_hidden, prob)

                    if GPU and cuda.is_available():
                        device = torch.device('cuda')
                    else:
                        device = torch.device('cpu')

                    model =model.to(device)

                    # train the network
                    train_losses, train_acc, valid_losses, valid_acc = train_model(model, train_data_split, validation_data, device, 
                                                                                   mini_batch_size,optimizer,criterion,n_epochs, 
                                                                                   eta,lambda_l2,alpha, beta)

                    # store train and test results 
                    train_results[idz,idx,idy,n,] = torch.tensor([train_losses, train_acc, valid_losses, valid_acc])
                    test_loss, test_acc = compute_metrics(model, test_data, device)
                    test_losses[idz,idx,idy,n] = test_loss
                    test_accuracies[idz,idx,idy,n] = test_acc
    
    # compute the validation mean accuracy and standard deviation of the accuracy
    validation_grid_mean_acc = torch.mean(train_results[:,:,:,:,3,39], dim= 3)
    validation_grid_std_acc = torch.std(train_results[:,:,:,:,3,39], dim= 3)
    
    # compute thetest mean accuracy and standard deviation of the accuracy
    train_grid_mean_acc = torch.mean(train_results[:,:,:,:,1,39], dim= 3)
    train_grid_std_acc = torch.std(train_results[:,:,:,:,1,39], dim= 3)
    
    # get the indices of the parameter with the highest mean validation accuracy
    idx = torch.where(validation_grid_mean_acc == validation_grid_mean_acc.max())

    if len(idx[0]) >=2:
                idx=idx[0]
    
    # get the tuned parameters
    opt_lr = lrs[idx[0].item()]
    opt_prob = drop_prob[idx[1].item()]
    opt_hidden_layer = hidden_layers[idx[2].item()]

    print('Best mean validation accuracy on {:d} seeds : {:.2f}%, std = {:.2f} with: learning rate = {:.4f} ,dropout rate = {:.2f} and nb_hidden = {:.2f}'.format(len(seeds), 
                        validation_grid_mean_acc[idx[0].item(), idx[1].item(),idx[2].item()], validation_grid_std_acc[idx[0].item(), idx[1].item(),idx[1].item()],opt_lr, opt_prob, opt_hidden_layer))
                    
    return train_results, test_losses, test_accuracies,opt_lr, opt_prob, opt_hidden_layer

###########################################################################################################################################

def grid_search_ws(lrs,drop_prob_ws, drop_prob_comp, seeds, mini_batch_size=100, optimizer = optim.Adam,criterion = nn.CrossEntropyLoss(), 
                   n_epochs=40, lambda_l2 = 0,alpha=0.5, beta=0.5, rotate = False,translate=False, swap_channel = False, GPU=False) :
    
    
    """
    
     General : Iterate over combinations of parameters list to optimize and repeat a 10 round training/validation procedure at each
               combination -> Select the combination with the highest validation accuracy for a LeNet_sharing network
               
               => only called in the <Nets> class by the Tune_LeNet_sharing function
               
     Input : 
         
         - lrs : list of learning rate
         - drop_prob_ws : list of dropout rate for the CNN part
         - drop_prob_comp : list of dropout rate for the FC layer part for binary classification
         - seeds : list of seeds for statistics 
         -> mini_batch_size,optimizer, criterion, n_epochs, eta, lambda_2, alpha, beta see training.py
         -> rotate,translate and swap_channels -> data augmentation see loader.py 
        
     Ouput :
         
         - train_results : A (len(lrs)xlen(drop_prob_ws)xlen(drop_prob_comp)xlen(seeds),4,n_epochs) tensor
                           len() -> number of parameters or seed
                           4 -> train loss ,train accuracy, validation loss, validation accuracy
                           n_epochs -> evolution during training
         - test_losses : A tensor of shape (10,) containing the test loss at each seed
         - test_accuracies : A tensor of shape (10,) containing the test loss at each seed
         - opt_lr : tuned value for learning rate 
         - opt_prob_ws : tuned value for drop_prob_ws
         - opt_prob_comp : tuned value for drop_prob_comp
    """
    # tensor to record the metrics
    train_results = torch.empty(len(lrs),len(drop_prob_ws),len(drop_prob_comp),len(seeds), 4, n_epochs)
    test_losses = torch.empty(len(lrs),len(drop_prob_ws), len(drop_prob_comp), len(seeds))
    test_accuracies = torch.empty(len(lrs),len (drop_prob_ws), len(drop_prob_comp), len(seeds))
    
    # iterate over the parameter combiantion for each seed in seeds
    for idz, eta in enumerate(lrs) :
        for idx,prob_ws in enumerate(drop_prob_ws):
            for idy,prob_comp in enumerate(drop_prob_comp) :
                for n, seed in enumerate(seeds):
                    print('lr : {:.4f} , prob_ws : {:.2f}, prob_comp : {:.2f} (n= {:d})'.format(eta,prob_ws, prob_comp, n))

                    # set seed
                    torch.manual_seed(seed)
                    torch.cuda.manual_seed(seed)
                    
                    #set the random seed 
                    random.seed(0)

                    # create the data
                    data = PairSetMNIST()
                    train_data = Training_set(data)
                    test_data = Test_set(data)
                    train_data_split =Training_set_split(train_data,rotate,translate,swap_channel)
                    validation_data= Validation_set(train_data)

                    # create the network
                    model = LeNet_sharing(dropout_ws = prob_ws,dropout_comp = prob_comp)

                    if GPU and cuda.is_available():
                        device = torch.device('cuda')
                    else:
                        device = torch.device('cpu')

                    model =model.to(device)

                    # train the network
                    train_losses, train_acc, valid_losses, valid_acc = train_model(model, train_data_split, validation_data, device, 
                                                                                   mini_batch_size,optimizer,criterion,n_epochs, 
                                                                                   eta,lambda_l2,alpha, beta)

                    # store train and test results 
                    train_results[idz,idx,idy,n,] = torch.tensor([train_losses, train_acc, valid_losses, valid_acc])
                    test_loss, test_acc = compute_metrics(model, test_data, device)
                    test_losses[idz,idx,idy,n] = test_loss
                    test_accuracies[idz,idx,idy,n] = test_acc
    
    # compute the validation mean accuracy and standard deviation of the accuracy
    validation_grid_mean_acc = torch.mean(train_results[:,:,:,:,3,39], dim= 3)
    validation_grid_std_acc = torch.std(train_results[:,:,:,:,3,39], dim= 3)
    
    # compute thetest mean accuracy and standard deviation of the accuracy
    train_grid_mean_acc = torch.mean(train_results[:,:,:,:,1,39], dim= 3)
    train_grid_std_acc = torch.std(train_results[:,:,:,:,1,39], dim= 3)
    
    # get the indices of the parameter with the highest mean validation accuracy
    idx = torch.where(validation_grid_mean_acc == validation_grid_mean_acc.max())

    if len(idx[0]) >=2:
                idx=idx[0]
    
    # get the tuned parameters
    opt_lr = lrs[idx[0].item()]
    opt_prob_ws = drop_prob_ws[idx[1].item()]
    opt_prob_comp = drop_prob_comp[idx[2].item()]
    
    print('Best mean validation accuracy on {:d} seeds : {:.2f}%, std = {:.2f} with: learning rate = {:.4f} ,dropout rate ws = {:.2f} and dropout rate comp = {:.2f}'.format(len(seeds), 
                        validation_grid_mean_acc[idx[0].item(), idx[1].item(),idx[2].item()], validation_grid_std_acc[idx[0].item(), idx[1].item(),idx[1].item()],opt_lr, opt_prob_ws, opt_prob_comp))
                    
    return train_results, test_losses, test_accuracies,opt_lr, opt_prob_ws, opt_prob_comp

###########################################################################################################################################

def grid_search_aux(lrs,drop_prob_aux, drop_prob_comp, seeds, mini_batch_size=100, optimizer = optim.Adam,criterion= nn.CrossEntropyLoss(),
                    n_epochs=40,lambda_l2 = 0, alpha=0.5, beta=0.5,rotate=False,translate=False, swap_channel = False, GPU=False):
    
    
    """
    
     General : Iterate over combinations of parameters list to optimize and repeat a 10 round training/validation procedure at each
               combination -> Select the combination with the highest validation accuracy for a LeNet_sharing_aux network
               
               => only called in the <Nets> class by the Tune_LeNet_sharing_aux function
               
     Input : 
         
         - lrs : list of learning rate
         - drop_prob_aux : list of dropout rate for the CNN auxiliary part
         - drop_prob_comp : list of dropout rate for the FC layer part for binary classification
         - seeds : list of seeds for statistics 
         -> mini_batch_size,optimizer, criterion, n_epochs, eta, lambda_2, alpha, beta see training.py
         -> rotate,translate and swap_channels -> data augmentation see loader.py 
        
     Ouput :
         
         - train_results : A (len(lrs)xlen(drop_prob_aux)xlen(drop_prob_comp)xlen(seeds),4,n_epochs) tensor
                           len() -> number of parameters or seed
                           4 -> train loss ,train accuracy, validation loss, validation accuracy
                           n_epochs -> evolution during training
         - test_losses : A tensor of shape (10,) containing the test loss at each seed
         - test_accuracies : A tensor of shape (10,) containing the test loss at each seed
         - opt_lr : tuned value for learning rate 
         - opt_prob_aux : tuned value for drop_prob_aux
         - opt_prob_comp : tuned value for drop_prob_comp
    """
    # tensor to record the metrics
    train_results = torch.empty(len(lrs),len(drop_prob_aux),len(drop_prob_comp),len(seeds), 4, n_epochs)
    test_losses = torch.empty(len(lrs),len(drop_prob_aux),len(drop_prob_comp),len(seeds))
    test_accuracies = torch.empty(len(lrs),len(drop_prob_aux),len(drop_prob_comp),len(seeds))
    
    # iterate over the parameter combiantion for each seed in seeds
    for idz,eta in enumerate(lrs) :
        for idx,prob_aux in enumerate(drop_prob_aux):
            for idy,prob_comp in enumerate(drop_prob_comp) :
                for n, seed in enumerate(seeds) :
                    print(' lr : {:.4f}, prob aux : {:.2f}, prob comp : {:.2f} (n= {:d})'.format(eta,prob_aux, prob_comp, n))


                    # set seed
                    torch.manual_seed(seed)
                    torch.cuda.manual_seed(seed)
                    
                    #set the random seed 
                    random.seed(0)

                    # create the data
                    data = PairSetMNIST()
                    train_data = Training_set(data)
                    test_data = Test_set(data)
                    train_data_split =Training_set_split(train_data,rotate,translate,swap_channel)
                    validation_data= Validation_set(train_data)

                    # create the network
                    model = LeNet_sharing_aux(drop_prob_aux = prob_aux,drop_prob_comp = prob_comp)

                    if GPU and cuda.is_available():
                        device = torch.device('cuda')
                    else:
                        device = torch.device('cpu')

                    model =model.to(device)

                    # train the network
                    train_losses, train_acc, valid_losses, valid_acc = train_model(model, train_data_split, validation_data, device, 
                                                                                   mini_batch_size,optimizer,criterion,n_epochs, 
                                                                                   eta,lambda_l2,alpha, beta)
                    
                    # store train and test results 
                    train_results[idz,idx,idy,n,] = torch.tensor([train_losses, train_acc, valid_losses, valid_acc])
                    test_loss, test_acc = compute_metrics(model, test_data, device)
                    test_losses[idz,idx,idy,n] = test_loss
                    test_accuracies[idz,idx,idy,n] = test_acc
    
    # compute the validation mean accuracy and standard deviation of the accuracy
    validation_grid_mean_acc = torch.mean(train_results[:,:,:,:,3,39], dim= 3)
    validation_grid_std_acc = torch.std(train_results[:,:,:,:,3,39], dim= 3)
    
    # compute thetest mean accuracy and standard deviation of the accuracy
    train_grid_mean_acc = torch.mean(train_results[:,:,:,:,1,39], dim= 3)
    train_grid_std_acc = torch.std(train_results[:,:,:,:,1,39], dim= 3)
    
    # get the indices of the parameter with the highest mean validation accuracy
    idx = torch.where(validation_grid_mean_acc == validation_grid_mean_acc.max())

    if len(idx[0]) >=2:
                idx=idx[0]
    
    # get the tuned parameters
    opt_lr = lrs[idx[0].item()]
    opt_prob_aux = drop_prob_aux[idx[1].item()]
    opt_prob_comp = drop_prob_comp[idx[2].item()]

    print('Best mean validation accuracy on {:d} seeds : {:.2f}%, std = {:.2f} with: learning rate = {:.4f}  dropout rate aux = {:.2f} and dropout rate comp = {:.2f}'.format(len(seeds), 
                        validation_grid_mean_acc[idx[0].item(), idx[1].item(),idx[2].item()], validation_grid_std_acc[idx[0].item(), idx[1].item(),idx[2].item()],opt_lr, opt_prob_aux, opt_prob_comp))
                    
    return train_results, test_losses, test_accuracies,opt_lr, opt_prob_aux, opt_prob_comp
###########################################################################################################################################