from unsloth import FastLanguageModel
from datasets import load_dataset
from trl.trainer.sft_trainer import SFTTrainer
from trl.trainer.sft_config import SFTConfig
import torch
import shutil

# 1. Load the base model
max_seq_length = 2048
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/llama-3-8b-bnb-4bit",
    max_seq_length = max_seq_length,
    dtype = None,
    load_in_4bit = True,
    device_map = "auto",
)

# 2. Add LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r = 16,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj"],
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = True,  # Satisfies strict boolean type checker
    random_state = 3407,
)

# 3. Format your custom training data
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

# Load your JSONL file 
dataset = load_dataset("json", data_files="train.jsonl", split="train")
dataset = dataset.map(formatting_prompts_func, batched = True)

# 4. Start the Training Process
trainer = SFTTrainer(
    model = model,
    processing_class = tokenizer,
    train_dataset = dataset,
    args = SFTConfig(
        dataset_text_field = "text",
        max_length = max_seq_length,  # Updated to match current SFTConfig parameter name
        dataset_num_proc = 2,
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        max_steps = 60,
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

# 6. Zip the folder and download it back to your laptop
print("Zipping the model for download...")
shutil.make_archive("my-trained-dispatch-model", 'zip', "./my-trained-dispatch-model")

try:
    from google.colab import files # type: ignore
    files.download("my-trained-dispatch-model.zip")
    print("Download initiated! Check your browser downloads.")
except Exception as e:
    print("Could not auto-download. Please right-click the zip file in the sidebar to download it manually.")