import heapq
from typing import Type, Dict, List, Tuple
from top_n_statistic import TopNFieldStatistic
from logline import LogLine

class TopNSectionsStatistic(TopNFieldStatistic):
    def get_field_from_logline(self, logline: Type[LogLine]):
        return logline.get_section()

    def print_top_n_field(self, top_n_fields: List[Tuple[str, int]], message: str):
        print('The top {} sections over the last {} seconds:'.format(self.n, self.statistic_delay))
        for section, count in top_n_fields:
            print('Section: {}, Hits: {}'.format(section, count))