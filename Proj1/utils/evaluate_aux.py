import torch 
from matplotlib import pyplot
import sys
import numpy as np
sys.path.append('..')
from torch import nn 
from torch.nn import functional as F
from torch import optim
import torch.utils.data as dt
from torch.utils.data import Dataset, DataLoader
from utils.loader import load,PairSetMNIST,Training_set,Test_set, Training_set_split,Validation_set
from utils.plot import learning_curve
from utils.metrics import accuracy, compute_nb_errors
import torch.cuda as cuda



# compute loss and accuracy given a model and test (or validation) data

def compute_metrics(model, Data, device, mini_batch_size=100, criterion = nn.CrossEntropyLoss()):
    
    """
    function to calculate prediction accuracy + loss of a cnn with auxiliary loss
    
    """
    data_loader = DataLoader(Data, batch_size=mini_batch_size, shuffle=True)
    model.eval()
    test_loss = 0
    nb_errors = 0
    
    with torch.no_grad():
        
        for i, data in enumerate(data_loader, 0):
            input_, target_, classes_ = data

            input_ = input_.to(device)
            target_ = target_.to(device)
            classes_ = classes_.to(device)

            _, _, output = model(input_) 
            batch_loss = criterion(output, target_)
            test_loss += batch_loss     
            nb_errors += compute_nb_errors(output, target_)
            
        acc = 100*(1 - (nb_errors/Data.len) )
        test_loss = test_loss/Data.len     # normalize loss
              
        return test_loss.item(), acc
    
##################################################################################################################################    
    
# simple validation 


def validate_model(net_type,training_function, mini_batch_size=100, optimizer = optim.SGD,
                 criterion = nn.CrossEntropyLoss(), n_epochs=40, eta=1e-1, lambda_l2 = 0, 
                 alpha=0.5, beta=0.5, plot=True,rotate = False,translate=False,swap_channel = False, GPU=False): 

    """ Training / validation over n_epochs + testing a full test set"""
    
    data = PairSetMNIST( rotate,translate,swap_channel)
    train_data = Training_set(data)
    test_data = Test_set(data)
    train_data_split =Training_set_split(train_data)
    validation_data= Validation_set(train_data)


    model = net_type()

    if GPU and cuda.is_available():
        device = torch.device('cuda')
    else:
        device = torch.device('cpu')


    model =model.to(device)
        
    train_losses, train_acc, valid_losses, valid_acc = training_function(model, train_data_split, validation_data, device, mini_batch_size, optimizer,criterion,n_epochs, eta,lambda_l2, alpha, beta)
    
    if plot:
        
        learning_curve(train_losses, train_acc, valid_losses, valid_acc)

    test_loss, test_accuracy = compute_metrics(model, test_data, device)
    
    print('\nTest Set | Loss: {:.4f} | Accuracy: {:.2f}%\n'.format(test_loss, test_accuracy))
    

########################################################################################################################################

# evaluation and final prediction statistics on large test set

def evaluate_model(net,training_function, seeds, mini_batch_size=100, optimizer = optim.SGD,
                 criterion = nn.CrossEntropyLoss(), n_epochs=40, eta=1e-1, 
                 lambda_l2 = 0, alpha=0.5, beta=0.5, plot=True,rotate = False,translate=False,swap_channel = False, GPU=False): 
    
    """ 10 rounds of training / validation + testing metrics statistics  """
    
    train_results = torch.empty(len(seeds), 4, n_epochs)
    test_losses = []
    test_accuracies = []
    
    for n, seed in enumerate(seeds):
    
        data = PairSetMNIST( rotate,translate,swap_channel)
        train_data = Training_set(data)
        test_data = Test_set(data)
        train_data_split =Training_set_split(train_data)
        validation_data= Validation_set(train_data)

        model = net()

        if GPU and cuda.is_available():
            device = torch.device('cuda')
        else:
            device = torch.device('cpu')


        model = model.to(device)

        train_losses, train_acc, valid_losses, valid_acc = training_function(model, train_data_split, validation_data, device, mini_batch_size, optimizer,criterion,n_epochs, eta,lambda_l2, alpha, beta)
        train_results[n,] = torch.tensor([train_losses, train_acc, valid_losses, valid_acc])
        test_loss, test_acc = compute_metrics(model, test_data, device)
        test_losses.append(test_loss)
        test_accuracies.append(test_acc)
        
        if plot:
            
            learning_curve(train_losses, train_acc, valid_losses, valid_acc)
            
            
        
        print('\nTrial {:d} | Test Loss: {:.4f} | Test Accuracy: {:.2f}%\n'.format(n, test_loss, test_acc))
        
    return train_results, torch.tensor(test_losses), torch.tensor(test_accuracies)

##########################################################################################################################################

def grid_search(net_type,training_function, drop_prob_aux, drop_prob_comp, seeds, mini_batch_size=100, optimizer = optim.SGD,
                 criterion = nn.CrossEntropyLoss(), n_epochs=40, eta=1e-1, 
                 lambda_l2 = 0, alpha=0.5, beta=0.5,rotate = False,translate=False,swap_channel = False, GPU=False):
    
    train_results = torch.empty(len(drop_prob_aux),len(drop_prob_comp),len(seeds), 4, n_epochs)
    test_losses = torch.empty(len(drop_prob_aux),len(drop_prob_comp),len(seeds))
    test_accuracies = torch.empty(len(drop_prob_aux),len(drop_prob_comp),len(seeds))
    
    for idx,prob_aux in enumerate(drop_prob_aux):
        for idy,prob_comp in enumerate(drop_prob_comp) :
            for n, seed in enumerate(seeds) :
                print('prob aux : {:.1f}, prob comp : {:.1f} (n= {:d})'.format(prob_aux, prob_comp, n))


                # set seed
                torch.manual_seed(seed)
                torch.cuda.manual_seed(seed)


                # create the data
                data = PairSetMNIST( rotate,translate,swap_channel)
                train_data = Training_set(data)
                test_data = Test_set(data)
                train_data_split =Training_set_split(train_data)
                validation_data= Validation_set(train_data)
                
                # create the network
                model = net_type(drop_prob_aux = prob_aux,drop_prob_comp = prob_comp)

                if GPU and cuda.is_available():
                    device = torch.device('cuda')
                else:
                    device = torch.device('cpu')

                model =model.to(device)
                
                # train the network
                train_losses, train_acc, valid_losses, valid_acc = training_function(model, train_data_split, validation_data, device, mini_batch_size, optimizer,criterion,n_epochs, eta,lambda_l2 ,alpha, beta)
                
                train_results[idx,idy,n,] = torch.tensor([train_losses, train_acc, valid_losses, valid_acc])
                test_loss, test_acc = compute_metrics(model, test_data, device)
                test_losses[idx,idy,n] = test_loss
                test_accuracies[idx,idy,n] = test_acc
        
    validation_grid_mean_acc = torch.mean(train_results[:,:,:,3,39], dim= 2)
    validation_grid_std_acc = torch.std(train_results[:,:,:,3,39], dim= 2)

    train_grid_mean_acc = torch.mean(train_results[:,:,:,1,39], dim= 2)
    train_grid_std_acc = torch.std(train_results[:,:,:,1,39], dim= 2)

    idx = torch.where(validation_grid_mean_acc == validation_grid_mean_acc.max())

    if len(idx[0]) >=2:
                idx=idx[0]

    drop_prob_aux = drop_prob_aux[idx[0].item()]
    drop_prob_comp = drop_prob_comp[idx[1].item()]

    print('Best mean validation accuracy on {:d} seeds : {:.2f}%, std = {:.2f} with: dropout rate = {:.2f} and nb_hidden = {:.2f}'.format(len(seeds), 
                        validation_grid_mean_acc[idx[0].item(), idx[1].item()], validation_grid_std_acc[idx[0].item(), idx[1].item()], drop_prob_aux, drop_prob_comp))
                    
    return train_results, test_losses, test_accuracies
        