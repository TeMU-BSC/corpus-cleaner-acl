import subprocess
import argparse
import os
from ..cleaner_component_reducer import CleanerComponentReducer
from typing import Optional
from glob import glob
from corpus_cleaner.par_utils import MappingPipeline, PipelineLogger


class DocumentFilter(CleanerComponentReducer):
    def __init__(self, args: argparse.Namespace, document_deduplication_threshold: float = 0.5,
                 dedup_buffer: int = 16777216,
                 remove_glob_rep_sen: int = 5, output_path: Optional[str] = None):
        # TODO: Modify "args.document_deduplication_threshold if args.document_deduplication_threshold is not None
        # else..." pattern
        self.only_reduce_ind_onion = args.only_reduce_ind_onion
        out_path = output_path if output_path is not None else args.output_path
        onion_input_file = os.path.join(out_path, 'input.onion')
        onion_output_file = os.path.join(out_path, 'output_deduplicate.onion.dedup')
        onion_output_dedup_sentences_file = os.path.join(out_path, 'output_deduplicate.onion.dedup.sentences')
        remove_glob_rep_sen = args.remove_glob_rep_sen if args.remove_glob_rep_sen is not None else remove_glob_rep_sen
        final_path = onion_output_file if remove_glob_rep_sen < 2 else onion_output_dedup_sentences_file
        if args.debug:
            extensions = '.debug'
        elif remove_glob_rep_sen < 2:
            extensions = '.dedup'
        else:
            extensions = '.sentences'
        extensions = (extensions,)
        super().__init__(args, format_='onion', tmp_file=onion_input_file, final_path=final_path,
                         input_path=out_path if not self.only_reduce_ind_onion else os.path.join(out_path, 'tmp'),
                         extensions=extensions)
        self.output_path = out_path
        self.document_deduplication_threshold = args.document_deduplication_threshold \
            if args.document_deduplication_threshold is not None else document_deduplication_threshold
        self.remove_glob_rep_sen = args.remove_glob_rep_sen \
            if args.remove_glob_rep_sen is not None else remove_glob_rep_sen
        self.dedup_buffer = args.dedup_buffer \
            if args.dedup_buffer is not None else dedup_buffer
        self.onion_input_file = onion_input_file
        self.onion_output_file = onion_output_file
        self.onion_path = os.path.join('lib', 'onion-1.2', 'bin', 'onion')
        self.onion_tmp = os.path.join(out_path, 'tmp')
        self.onion_output_dedup_sentences_file = onion_output_dedup_sentences_file




    @staticmethod
    def add_args(parser: argparse.ArgumentParser):
        parser.add_argument('--document-deduplication-threshold', type=float,
                            help='Threshold for document de-duplication, expressed as the percentage of sentences'
                                 'overlap between documents',
                            default=0.5)
        parser.add_argument('--remove-glob-rep-sen', type=int, default=-1,
                            help='Whether to remove corpus-level repeated sentences (threshold of repetitions; -1'
                                 'to deactivate)')
        parser.add_argument('--dedup-buffer', type=int, default=1000000000,
                            help='Deduplication buffer size, in bytes (default: 1000000000)')
        parser.add_argument('--only-reduce-ind-onion', action='store_true', help='Individually apply reduction')

    @staticmethod
    def check_args(args: argparse.Namespace):
        # TODO check custom args
        pass

    def _run_onion(self):
        cat_command = "find " + self.onion_tmp + " -name '*.onion' -exec cat {} \; > " + self.onion_input_file
        add_doc_tags = f"sed -i '1i <corpora>' {self.onion_input_file}; echo '</corpora>' >> {self.onion_input_file}"
        subprocess.run(cat_command, shell=True, check=True, universal_newlines=True)
        subprocess.run(add_doc_tags, shell=True, check=True, universal_newlines=True)
        onion_command = f'{self.onion_path} -d "corpora" -p "doc" -t {self.document_deduplication_threshold} -n 5 -b {self.dedup_buffer} ' \
                        f'{self.onion_input_file} > {self.onion_output_file}'
        subprocess.run(onion_command, shell=True, check=True, universal_newlines=True)

    def _remove_global_duplicate_sentences(self, threshold: int):
        # First, remove format-control letters to prevent errors in the awk script
        remove_format_modifiers_command = f"sed -i 's/%/___PERCENTAGE___/g' {self.onion_output_file}"
        subprocess.run(remove_format_modifiers_command, shell=True, check=True, universal_newlines=True)

        # Then, deduplicate with gawk command
        awk = '''{
                    switch($0)
                    {
                    case /0\t</:
                        print
                        break
                    case /0\t/:
                        seen[$0]++
                        {if (seen[$0] <= ''' + str(threshold) + ''') {print} else {printf "1" "\t"; for (i=2; i<NF; i++) printf $i " "; print $NF}}
                        break
                    default:
                        print
                        break
                    }
                }
        '''
        awk_path = os.path.join(self.output_path, 'script.awk')
        with open(awk_path, 'w') as f:
            f.write(awk)
        command = f"gawk -f {awk_path} {self.onion_output_file} > {self.onion_output_dedup_sentences_file}"
        subprocess.run(command, shell=True, check=True, universal_newlines=True)
        demask_command = f"sed -i 's/___PERCENTAGE___/%/g' {self.onion_output_dedup_sentences_file}"
        subprocess.run(demask_command, shell=True, check=True, universal_newlines=True)
        os.remove(awk_path)

    def get_onion_files_paths(self):
        paths = []
        for path in glob(os.path.join(self.onion_tmp, '*.onion')):
            paths.append(path)
        return paths

    def run_single_onion_dedup_txt(self, path: str):
        # Onion
        onion_output_file = f'{path}.dedup'
        onion_command = f'{self.onion_path} -m -n 1 -t {self.document_deduplication_threshold} -b {self.dedup_buffer} ' \
                        f'{path} > {onion_output_file}'
        subprocess.run(onion_command, shell=True, check=True, universal_newlines=True)

        # Awk
        # First, remove format-control letters to prevent errors in the awk script
        if self.remove_glob_rep_sen != -1:
            threshold = self.remove_glob_rep_sen
            remove_format_modifiers_command = f"sed -i 's/%/___PERCENTAGE___/g' {onion_output_file}"
            subprocess.run(remove_format_modifiers_command, shell=True, check=True, universal_newlines=True)

            # Then, deduplicate with gawk command
            awk = '''{
                                switch($0)
                                {
                                case /0\t</:
                                    print
                                    break
                                case /0\t/:
                                    seen[$0]++
                                    {if (seen[$0] <= ''' + str(threshold) + ''') {print} else {printf "1" "\t"; for (i=2; i<NF; i++) printf $i " "; print $NF}}
                                    break
                                default:
                                    print
                                    break
                                }
                            }
                    '''
            awk_path = os.path.join(self.output_path, f'script{str(os.getpid())}.awk')
            with open(awk_path, 'w') as f:
                f.write(awk)
            onion_output_dedup_sentences_file = onion_output_file + '.sentences'
            command = f"gawk -f {awk_path} {onion_output_file} > {onion_output_dedup_sentences_file}"
            subprocess.run(command, shell=True, check=True, universal_newlines=True)
            demask_command = f"sed -i 's/___PERCENTAGE___/%/g' {onion_output_dedup_sentences_file}"
            subprocess.run(demask_command, shell=True, check=True, universal_newlines=True)
            os.remove(awk_path)


    def create_pipeline_reducer_mappers(self):
        return [self.run_single_onion_dedup_txt]

    def _reduce(self):
        if self.only_reduce_ind_onion:
            self.get_onion_files_paths()
            self.args.logger.logger.info('Distributed reduce')
            pipeline = MappingPipeline(streams=self.get_onion_files_paths(),
                                       mappers_factory=self.create_pipeline_reducer_mappers,
                                       parallel=self.args.parallel,
                                       logger=self.args.logger if self.args.log_every_iter != -1 else None,
                                       log_every_iter=self.args.log_every_iter,
                                       backend=self.args.backend,
                                       checkpoint_path=None)
            pipeline.run()
        else:
            self._run_onion()
            if self.remove_glob_rep_sen != -1:
                self._remove_global_duplicate_sentences(self.remove_glob_rep_sen)
