from .data_parser import DataParser
from typing import Iterable
from corpus_cleaner.document import Document
from typing import TextIO
from typing import Tuple
import argparse
from typing import Optional


class OnionParser(DataParser):
    def __init__(self, args: argparse.Namespace, extensions: Tuple[str] = ('.dedup',),
                 input_path: Optional[str] = None,
                 **kwargs):
        super(OnionParser, self).__init__(args, encoding='utf-8',
                                          input_path=args.output_path if input_path is None else input_path,
                                          extensions=extensions, **kwargs)

    def _parse_file(self, fd: TextIO, relative_filepath: str, idx_filepath: int) -> Iterable[Document]:
        doc_sentences = []
        par_words = []
        doc = Document(content='')
        for line in fd:
            if not self.debug:
                line_index = line.split('\t')[0]
                line = '\t'.join(line.split('\t')[1:])

            # ignore the first two lines with the start tags
            if line.startswith('<doc'):
                sp = line.split()
                if len(sp) > 2:
                    doc = Document.parse_str(sp[1:-1])
                else:
                    doc = Document(content='')

            # If words in paragraph, merge words of paragraphs to create the sentence paragraph
            # based on \n as document boundary and empty the list of words.
            # Empty the document sentences list when a new document is reached (</p> tag) and return the document object
            elif line  in ['</doc>\n', '\n']:
                if par_words:
                    par_sentence = ' '.join(par_words)
                    doc_sentences.append(par_sentence)
                    par_words = []
                    if line == '</doc>\n':
                        doc.sentences = doc_sentences
                        yield doc
                        doc_sentences = []
            elif line in ['<corpora>\n', '</corpora>\n', '<doc>\n']:
                continue

            else:
                if self.debug or line_index == '0':
                    par_words.append(line.strip('\n'))
