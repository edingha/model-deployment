import Algorithmia
import argparse
from Algorithmia.errors import AlgorithmException

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--api_key", nargs="?")
    parser.add_argument("-u", "--username", nargs="?")
    parser.add_argument("-a", "--algoname", nargs="?")
    parser.add_argument("-m", "--model_script", nargs="?")
    parser.add_argument("-d", "--model_dependency_file", nargs="?")
    parser.add_argument("-p", "--data_path", nargs="?", default=".my/mycollection")
    
    args = parser.parse_args()
    return args

def main(args=None):
    if isinstance(args, type(None)):
        args = parse_arguments()
        deploy(args)

def deploy(args):
    # A data collection, where we'll be storing our files
    data_path = "data://{}".format(args.data_path)

    # Create a new algorithmia client
    client = Algorithmia.client(args.api_key)

    # Create data collection if it doesn't exist
    if not client.dir(data_path).exists():
        client.dir(data_path).create()

    ### 2. Create local directory for algorithm files ###

    import os
    import shutil

    # Define local work directory
    local_dir = "algo"

    # Delete local directory if it already exists
    if os.path.exists(local_dir):
        shutil.rmtree(local_dir)

    # Create local work directory
    os.makedirs(local_dir)

    ### 3. Upload model file ###

    model_name = "text_classification_model.h5"
    local_model = "{}/{}".format(local_dir, model_name)
    data_model = "{}/{}".format(data_path, model_name)

    # Serialize the model locally
    model.save(local_model)

    # Upload our model file to our data collection
    _ = client.file(data_model).putFile(local_model)

    ### 4. Upload word index ###

    import pickle

    word_index_name = "word_index.pickle"
    local_word_index = "{}/{}".format(local_dir, word_index_name)
    data_word_index = "{}/{}".format(data_path, word_index_name)

    # Serialize (pickle) our word index
    with open(local_word_index, "wb") as fh:
        pickle.dump(word_index, fh)

    # Upload word index file to our data collection
    _ = client.file(data_word_index).putFile(local_word_index)

    ### 5. Create new algorithm ###

    # Algorithms are refered with the following schema: username/algoname
    algo_namespace = "{}/{}".format(args.username, args.algoname)

    # Here are some details you can define for your algorithm
    details = {
        "summary": "This algorithms returns the sentiment of movie reviews.",
        "label": "Movie Review Sentiment Analysis",
        "tagline": "movie_review_sentiment"
    }

    # 1. We're making our algorithm closed-sourced – "source_visibility"
    # 
    # 2. We're selecting a package set that has tensorflow-gpu already installed. – "package_set"
    #    Even though we could manually install it later, using the optimized
    #    & pre-installed image allows you to compile things faster.
    # 
    # 3. We're selectig the Algorithmia Platform License (aka. "apl"). – "license"
    # 
    # 4. We're giving our algorithm internet access. – "network_access"
    # 
    # 5. We're allowing our algorithm to call other algorithms. – "pipeline_enabled"
    settings = {
        "source_visibility": "closed",
        "package_set": "tensorflow-gpu-1.12",
        "license": "apl",
        "network_access": "full",
        "pipeline_enabled": True
    }

    # Let's also provide a sample input for our algorithm
    version_info = {
        "sample_input": '{\n    "text": "This is a positive review. I really liked it! It was great!"\n}'
    }

    print("Algorithm namepace: {}".format(algo_namespace))

    # Create a new algorithm
    client.algo(algo_namespace).create(details, settings, version_info)

    # Print the URL to the algorithm
    print("Algorithm URL: https://algorithmia.com/algorithms/{}".format(algo_namespace))

    ### 6. Git clone our algorithm locally  ###

    import urllib.parse
    from git import Git, Repo, remote

    # Encode API key, so we can use it in the git URL
    encoded_api_key= urllib.parse.quote_plus(args.api_key)

    algo_repo = "https://{}:{}@git.algorithmia.com/git/{}/{}.git".format(args.username, encoded_api_key, args.username, args.algoname)

    _ = Repo.clone_from(algo_repo, "{}/{}".format(local_dir, args.algoname))

    cloned_repo = Repo("{}/{}".format(local_dir, args.algoname))

    ### 7. The algorithm script & dependency file ###

    algo_script_path = "{}/{}/src/{}.py".format(local_dir, args.algoname, args.algoname)
    dependency_file_path = "{}/{}/{}".format(local_dir, args.algoname, "requirements.txt")

    shutil.copyfile(args.model_script, algo_script_path)
    shutil.copyfile(args.model_dependency_file, dependency_file_path)

    ### 8. Upload our source code ###

    files = ["src/{}.py".format(args.algoname), "requirements.txt"]
    cloned_repo.index.add(files)

    cloned_repo.index.commit("Add algorithm files")

    origin = cloned_repo.remote(name='origin')
    
    print("Pushing source code upstream, uploading model file & compiling algorithm...")
    
    _ = origin.push()

    # Print the URL to the algorithm source code
    print("Algorithm Source Code is available at: https://algorithmia.com/algorithms/{}/source".format(algo_namespace))

    ### 9. Call & test our algorithm ###
    
    print("Testing new compiled algorithm via API endpoint...")
    latest_hash = client.algo(algo_namespace).info().version_info.git_hash

    # Call algorithm until the algo hash endpoint becomes available, up to 10 seconds
    @retry(AlgorithmException, tries=10, delay=1)
    def get_probability(ALGO, VERSION, INPUT):
        return client.algo("{}/{}".format(ALGO, VERSION)).pipe(INPUT).result["prob"]

    algo_input = {
        "text": "This is a very positive review for the movie. I absolutely loved it!"
    }

    # Call the algorithm endpoint with the latest hash
    prob = get_probability(algo_namespace, latest_hash, algo_input)

    print("Test complete!")

    ### 10. Publish our algorithm ###
    
    print("Publishing and deploying algorithm...")

    # Now let's publish/deploy our algorithm
    client.algo(algo_namespace).publish()

    latest_version = client.algo(algo_namespace).info().version_info.semantic_version

    # Call the algorithm endpoint with the latest version
    prob = get_probability(algo_namespace, latest_version, algo_input)

    print("Algorithm has been deployed!")

if __name__ == "__main__":
    main()
