from collections import OrderedDict
from dataset import T5_Dataset
from transformers import T5Tokenizer, T5Config, T5ForConditionalGeneration
from noam_lr_scheduler import NoamLR
import torch
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm
from transformers import Adafactor
import transformers
from accelerate import Accelerator
import argparse
import os
from utils_accelerate import *
from tqdm.auto import tqdm


parser = argparse.ArgumentParser()
parser.add_argument('--save_prefix',type=str,
                    default='temp',
                    help='prefix of model save checkpoint')

parser.add_argument('--load_checkpoint',type=str,
                    default=None,
                    help='checkpoint to load from')

parser.add_argument('--model_size',type=str,
                    default='small',
                    help='T5 model size')

parser.add_argument('--optimizer',type=str,
                    default='adafactor',
                    help='which optimizer')

parser.add_argument('--dataset',type=str,
                    default='codex-m',
                    help='which dataset')

parser.add_argument('--resume',type=str,
                    default=None,
                    help='folder from which to resume run')

parser.add_argument('--learning_rate',type=float,
                    default=None,
                    help='learning rate')

parser.add_argument('--batch_size',type=int,
                    default=64,
                    help='train batch size')

parser.add_argument('--epochs',type=int,
                    default=5,
                    help='epochs')

parser.add_argument('--max_checkpoints',type=int,
                    default=5,
                    help='maximum no. of checkpoints to save')

parser.add_argument('--num_workers',type=int,
                    default=3,
                    help='num workers per gpu')

parser.add_argument('--save_steps',type=int,
                    default=5000,
                    help='num batches before checkpoint save')

parser.add_argument('--loss_steps',type=int,
                    default=500,
                    help='num batches before printing loss')

args = parser.parse_args()

accelerator = Accelerator()
device = accelerator.device


def save_accelerator_model(model, optimizer, steps, loss, args):
    # TODO:check how many models of that name exist
    # delete the last k
    folder_name = 'models/{}'.format(args.save_prefix)
    try:
        os.mkdir(folder_name)
    except:
        pass
    file_name = '{}/{}.pt'.format(folder_name, steps)
    checkpoint = { 
    'steps': steps,
    'model': model.state_dict(),
    'optimizer': optimizer.state_dict(),
    'loss': loss,
    'args': args} # also saving the command line args
    accelerator.save(checkpoint, file_name)
    print('Model/optimizer saved at {}'.format(file_name))
    

def train(model, optimizer, dataset, args=None):
    num_workers = args.num_workers
    batch_size = args.batch_size
    loss_steps = args.loss_steps
    save_steps = args.save_steps
    num_steps = args.start_steps
    data_loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers,
                            collate_fn=dataset._collate_fn_new)
    model, optimizer, data_loader = accelerator.prepare(model, optimizer, data_loader)
    # model, optimizer, _, _ = load_accelerator_model('models/codex-m_6gpu/17500.pt')
    model.to(device)
    model.train()
    
    for epoch in range(args.epochs):
        loader = tqdm(data_loader, total=len(data_loader), unit="batches")
        running_loss = 0
        for steps, batch in enumerate(loader):
            input_ids, attention_mask, labels, labels_attention_mask = batch
            optimizer.zero_grad()
            outputs = model(input_ids = input_ids.to(device), 
            attention_mask = attention_mask.to(device), 
            labels= labels.to(device)
            )
            loss = outputs.loss
            accelerator.backward(loss)
            optimizer.step()
            if num_steps % save_steps == 0:
                print('Saving at step %d' % num_steps)
                save_accelerator_model(model, optimizer, num_steps, loss.item(), args)
            num_steps += 1
            if num_steps % loss_steps == 0:
                # accelerator.print('Loss: ', running_loss/loss_steps)
                print('Loss: ', loss.item()/len(input_ids)) # divide by batch size
                running_loss = 0
            running_loss += loss.item()
            
        print('epoch loss ', running_loss)


train_dataset = T5_Dataset('train', dataset_name=args.dataset)
print('Train dataset size: ', len(train_dataset))
args.start_steps = 0
if 't5' not in args.model_size: # TODO: remove the need for this
    args.model_size = 't5-{}'.format(args.model_size)
config = T5Config().from_pretrained(args.model_size)
model = T5ForConditionalGeneration(config)
print('Model : ', model.config)

if args.optimizer == 'adafactor':
    if args.learning_rate == None:
        # optimizer = Adafactor(model.parameters(), relative_step=True, warmup_init=True)
        optimizer = Adafactor(model.parameters(), scale_parameter=True, relative_step=True, warmup_init=True, lr=None)
    else:
        # optimizer = Adafactor(model.parameters(), lr=args.learning_rate, relative_step=False, warmup_init=False)
        optimizer = Adafactor(model.parameters(), scale_parameter=False, relative_step=False, warmup_init=False, lr=args.learning_rate)
elif args.optimizer == 'adam':
    optimizer = transformers.AdamW(model.parameters(), lr=args.learning_rate)
else:
    print('Unknown optimizer type %s' % args.optimizer)
    exit(0)

if args.resume != None:
    # see if folder of resume exists
    if os.path.exists('model/{}'.format(args.resume)):
        exit(0) #TODO: write this
    else:
        print('Folder %s not found' % args.resume)
        exit(0)
elif args.load_checkpoint != None:
    print('Loading from {}'.format(args.load_checkpoint))
    model, optimizer, _, _ = load_accelerator_model('models/{}'.format(args.load_checkpoint))
    print('Loaded')
else:
    print('Starting fresh')
    
train(model, optimizer, train_dataset, args)
