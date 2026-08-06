from unsloth import FastLanguageModel
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments
import torch

# 1. Load the base model
max_seq_length = 2048
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/llama-3-8b-bnb-4bit", # 4-bit quantization saves RAM
    max_seq_length = max_seq_length,
    dtype = None,
    load_in_4bit = True,
)

# 2. Add LoRA adapters (This is the part that isolates and learns your specific style)
model = FastLanguageModel.get_peft_model(
    model,
    r = 16, 
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj"],
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",
    random_state = 3407,
)

# 3. Format your custom training data
# This template tells the model exactly how to map the dashboard data to your emails
alpaca_prompt = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
Write a personalized dispatching offer email.

### Input:
{}

### Response:
{}"""

def formatting_prompts_func(examples):
    inputs = examples["prompt"]
    outputs = examples["completion"]
    texts = []
    for input_text, output_text in zip(inputs, outputs):
        text = alpaca_prompt.format(input_text, output_text) + tokenizer.eos_token
        texts.append(text)
    return { "text" : texts }

# Load your local JSONL file
dataset = load_dataset("json", data_files="train.jsonl", split="train")
dataset = dataset.map(formatting_prompts_func, batched = True)

# 4. Start the Training Process
trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    dataset_num_proc = 2,
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        max_steps = 60, # Increase this to 100+ if you have a larger dataset
        learning_rate = 2e-4,
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
    ),
)

print("Starting training...")
trainer.train()

# 5. Save your trained model locally
print("Saving custom model...")
model.save_pretrained("./my-trained-dispatch-model")
tokenizer.save_pretrained("./my-trained-dispatch-model")
print("Done! You can now load this folder into your FastAPI script.")