# Text-Align
A scalable and high-performance sequence aligner for large collections of texts

Built in collaboration with <a href="https://www.lip6.fr/?LANG=en">LIP6</a>

For docs in French see [here](docs/french/quickstart.md)

## Installation ##

Note that Text-Align will only run on 64 bit Linux and MacOS. Windows will NOT be supported.

- Run install.sh script. This should install all needed components
- Make sure you include /etc/text-align/apache_wsgi.conf in your main Apache configuration file to enable searching
- Install node and npm for the web application build system

## Quick start ##

The sequence aligner is executed via the `textalign` command.

`textalign` takes the following command-line arguments:

* `--config`: path to the configuration file where preprocessing, matching, and web application settings are set
* `--source_files`: path to source files
* `--source_metadata`: path to source metadata
* `--target_files`: path to target files
* `--target-metadata`: path to target metadata
* `--is_philo_db`: Define if files are from a PhiloLogic database. If so, no need to define metadata arguments. Set to False by default.
* `--output_path`: path to results
* `--debug`: turn on debugging
* `--workers`: Set number of workers/threads.
* `--load_web_app`: Define whether to load results into a database viewable via a web application. Set to True by default.


Example:

`textalign --source_files=/path/to/source/files --target_files=/path/to/target/files --source_metadata=/path/to/source/metadata.json --target_metadata=/path/to/target/metadata.json --config=config.ini --workers=6 --output_path=/path/to/output`

## Run comparison between preprocessed files manually ##

It's possible run a comparison between documents without having to regenerate ngrams. This comparison is done using the `compareNgrams` command. 

`compareNgrams` takes the following arguments:

* `--source_files`: path to source ngrams generated by `textalign`
* `--target_files`: path to target ngrams generated by `textalign`. If this option is not defined, the comparison will be done between source files.
* `--source_metadata`: path to source metadata, a required parameter
* `--target_metadata`: path to target metadata, a required parameter if target files are defined.
* `--output_path`: path to results
* `--debug`: turn on debugging
* `--threads`: Number of threads to allocate for comparison.

Many more options are available, execute `compareNgrams -h` to see them all.


Example:

`compareNgrams --source_files=montesquieu/ngrams/* --target_files=encyclopedie/ngrams/* --threads=10 --output_path=results/


