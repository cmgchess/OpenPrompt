
# # Conditional Generation with Prefix Tuning.
# In this tutorial, we do conditional generation with prefix tuning template.

# we use WebNLG as an example, as well. Note that the evaluation of generation result should be done
# by using the scripts provided by https://github.com/Yale-LILY/dart/tree/master/evaluation, 
# Which we do not include in it. 

from openprompt.data_utils.conditional_generation_dataset import WebNLGProcessor
dataset = {}
dataset['train'] = WebNLGProcessor().get_train_examples("./datasets/CondGen/webnlg_2017/")
dataset['validation'] = WebNLGProcessor().get_dev_examples("./datasets/CondGen/webnlg_2017/")
dataset['test'] = WebNLGProcessor().get_test_examples("./datasets/CondGen/webnlg_2017/")


# load a pretrained model, its tokenizer, its config, and its TokenzerWrapper by one function 
from openprompt.plms import load_plm
plm, tokenizer, model_config, WrapperClass = load_plm("gpt2", "gpt2-medium")


# Instantiating the PrefixTuning Template !
from openprompt.prompts import PrefixTuningTemplate
# we can use a plain text as the default setting
# i.e. 
# mytemplate = PrefixTuningTemplate(model=plm, tokenizer=tokenizer)
# is equal to 
# mytemplate = PrefixTuningTemplate(model=plm, tokenizer=tokenizer, text='{"placeholder":"text_a"} {"mask"}')
mytemplate = PrefixTuningTemplate(model=plm, tokenizer=tokenizer, text='{"placeholder":"text_a"} Make a sentence {"mask"}')

# To better understand how does the template wrap the example, we visualize one instance.
wrapped_example = mytemplate.wrap_one_example(dataset['train'][0]) 
print(wrapped_example)


# Your can loop over the dataset by yourself by subsequently call mytemplate.wrap_one_example  and WrapperClass().tokenizer()
# but we have provide a PromptDataLoader for you.
from openprompt import PromptDataLoader
train_dataloader = PromptDataLoader(dataset=dataset["train"], template=mytemplate, tokenizer=tokenizer, 
    tokenizer_wrapper_class=WrapperClass, max_seq_length=256, decoder_max_length=256, 
    batch_size=4,shuffle=True, teacher_forcing=True, predict_eos_token=True,
    truncate_method="head")

# load the pipeline model PromptForGeneration.
from openprompt import PromptForGeneration
use_cuda = True
prompt_model = PromptForGeneration(plm=plm,template=mytemplate, freeze_plm=True,tokenizer=tokenizer)
if use_cuda:
    prompt_model=  prompt_model.cuda()

from transformers import AdamW
# Follow PrefixTuning（https://github.com/XiangLi1999/PrefixTuning), we also fix the language model
# only include the template's parameters in training. 
optimizer_grouped_parameters2 = [
    {'params': [p for n,p in prompt_model.template.named_parameters() if "raw_embedding" not in n]}
]

#
optimizer = AdamW(optimizer_grouped_parameters2, lr=1e-3)

for epoch in range(10):
    tot_loss = 0 
    for step, inputs in enumerate(train_dataloader):
        if use_cuda:
            inputs = inputs.cuda()
        loss = prompt_model(inputs)
        loss.backward()
        tot_loss += loss.item()
        optimizer.step()
        optimizer.zero_grad()
        if step %100 ==1:
            print("Epoch {}, average loss: {}".format(epoch, tot_loss/(step+1)), flush=True)

validation_dataloader = PromptDataLoader(dataset=dataset["validation"], template=mytemplate, tokenizer=tokenizer, 
    tokenizer_wrapper_class=WrapperClass, max_seq_length=256, decoder_max_length=256, 
    batch_size=4,shuffle=False, teacher_forcing=False, predict_eos_token=True,
    truncate_method="head")

generation_arguments = {
    "max_length": 512,
    "max_new_tokens": None,
    "min_length": 5,
    "temperature": 1.0,
    "do_sample": False,
    "top_k": 0,
    "top_p": 0.9,
    "repetition_penalty": 1.0,
    "num_beams": 5,
    "bad_words_ids": None
}

generated_sentence = []
groundtruth_sentence = []

for step, inputs in enumerate(validation_dataloader):
    if use_cuda:
        inputs = inputs.cuda()
    _, output_sentence = prompt_model.generate(inputs, **generation_arguments)
    generated_sentence.append(output_sentence)
    groundtruth_sentence.append(inputs['tgt_text'])

from openprompt.utils.metrics import generation_metric

score = generation_metric(generated_sentence, groundtruth_sentence, "sentence_bleu")
print(score)

