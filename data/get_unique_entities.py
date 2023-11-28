import argparse
import os
from tqdm.auto import tqdm
import re

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, default="codex-m")
    args = parser.parse_args()
    dataset_name = args.dataset

    train_file = open(os.path.join(dataset_name, "train.txt"))
    valid_file = open(os.path.join(dataset_name, "valid.txt"))
    test_file = open(os.path.join(dataset_name, "test.txt"))
    output_file = os.path.join(dataset_name, "entity_strings.txt")
    start_separator = ": "
    unique_entities = set()
    files = [train_file, valid_file, test_file]

    for input_file in files:
        line_count = len(input_file.readlines())
        input_file.seek(0)
        for line in tqdm(input_file, total=line_count):
                sentence = line[line.find(start_separator)+len(start_separator):]
                split_sentence = [ s.strip() for s in sentence.split(" | ")]
                # print(split_sentence)
                for s in split_sentence:
                    if s.find("\t")!=-1:
                        unique_entities.add(s.split("\t")[1])
                    else:
                        unique_entities.add(s)



    with open(output_file, "w") as out_file:
        for entity in unique_entities:
            out_file.write(entity + "\n")
