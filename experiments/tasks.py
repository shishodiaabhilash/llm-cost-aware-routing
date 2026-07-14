"""
Built-in coding tasks for the Smart LLM Router experiment.

Each task has:
  - id:          short identifier
  - difficulty:  'easy' | 'medium' | 'hard'  (ground-truth label, for analysis)
  - entry:       the function name the model must implement
  - prompt:      the natural-language problem statement
  - tests:       Python assert statements that validate a candidate solution

The 'tests' string is executed together with the model's code inside an
isolated subprocess (see router_experiment.py). This is real code execution of
model-generated code -- see the security note in router_experiment.py.
"""

TASKS = [
    dict(
        id="add", difficulty="easy", entry="add",
        prompt="Write a function add(a, b) that returns the sum of two numbers.",
        tests="assert add(2,3)==5\nassert add(-1,1)==0\nassert add(0,0)==0",
    ),
    dict(
        id="reverse", difficulty="easy", entry="reverse_string",
        prompt="Write a function reverse_string(s) that returns the string s reversed.",
        tests="assert reverse_string('abc')=='cba'\nassert reverse_string('')==''\nassert reverse_string('a')=='a'",
    ),
    dict(
        id="is_even", difficulty="easy", entry="is_even",
        prompt="Write a function is_even(n) that returns True if n is even, else False.",
        tests="assert is_even(4)==True\nassert is_even(7)==False\nassert is_even(0)==True",
    ),
    dict(
        id="count_vowels", difficulty="easy", entry="count_vowels",
        prompt="Write a function count_vowels(s) that returns the number of vowels (a,e,i,o,u) in the string s, case-insensitive.",
        tests="assert count_vowels('hello')==2\nassert count_vowels('XYZ')==0\nassert count_vowels('AEIou')==5",
    ),
    dict(
        id="fib", difficulty="medium", entry="fib",
        prompt="Write a function fib(n) that returns the n-th Fibonacci number (0-indexed, fib(0)=0, fib(1)=1).",
        tests="assert fib(0)==0\nassert fib(1)==1\nassert fib(10)==55\nassert fib(15)==610",
    ),
    dict(
        id="is_prime", difficulty="medium", entry="is_prime",
        prompt="Write a function is_prime(n) that returns True if n is a prime number, else False.",
        tests="assert is_prime(2)==True\nassert is_prime(1)==False\nassert is_prime(17)==True\nassert is_prime(18)==False",
    ),
    dict(
        id="two_sum", difficulty="medium", entry="two_sum",
        prompt="Write a function two_sum(nums, target) that returns a list of two indices [i, j] such that nums[i]+nums[j]==target. Assume exactly one solution and i<j.",
        tests="assert two_sum([2,7,11,15],9)==[0,1]\nassert two_sum([3,2,4],6)==[1,2]\nassert two_sum([3,3],6)==[0,1]",
    ),
    dict(
        id="valid_parens", difficulty="medium", entry="valid_parens",
        prompt="Write a function valid_parens(s) that returns True if the string s of brackets '()[]{}' is validly balanced and nested, else False.",
        tests="assert valid_parens('()')==True\nassert valid_parens('()[]{}')==True\nassert valid_parens('(]')==False\nassert valid_parens('([)]')==False\nassert valid_parens('{[]}')==True",
    ),
    dict(
        id="lcs", difficulty="hard", entry="lcs",
        prompt="Write a function lcs(a, b) that returns the length of the longest common subsequence of strings a and b. Use dynamic programming for efficiency on longer inputs.",
        tests="assert lcs('abcde','ace')==3\nassert lcs('abc','abc')==3\nassert lcs('abc','def')==0\nassert lcs('AGGTAB','GXTXAYB')==4",
    ),
    dict(
        id="merge_intervals", difficulty="hard", entry="merge_intervals",
        prompt="Write a function merge_intervals(intervals) that takes a list of [start,end] intervals and returns the list of merged, non-overlapping intervals sorted by start.",
        tests="assert merge_intervals([[1,3],[2,6],[8,10],[15,18]])==[[1,6],[8,10],[15,18]]\nassert merge_intervals([[1,4],[4,5]])==[[1,5]]\nassert merge_intervals([[1,4],[0,4]])==[[0,4]]",
    ),
    dict(
        id="word_break", difficulty="hard", entry="word_break",
        prompt="Write a function word_break(s, words) that returns True if the string s can be segmented into a space-separated sequence of one or more words from the list 'words'. Use dynamic programming.",
        tests="assert word_break('leetcode',['leet','code'])==True\nassert word_break('applepenapple',['apple','pen'])==True\nassert word_break('catsandog',['cats','dog','sand','and','cat'])==False",
    ),
    dict(
        id="edit_distance", difficulty="hard", entry="edit_distance",
        prompt="Write a function edit_distance(a, b) that returns the Levenshtein edit distance between strings a and b (min insertions, deletions, substitutions). Use dynamic programming.",
        tests="assert edit_distance('horse','ros')==3\nassert edit_distance('intention','execution')==5\nassert edit_distance('','abc')==3\nassert edit_distance('abc','abc')==0",
    ),
]

# ---------------------------------------------------------------------------
# Harder problems: multi-step reasoning, tricky edge cases, and non-obvious
# algorithms. A small local model (e.g. llama3.2 3B) is expected to fail several
# of these, forcing the router to escalate, while a strong code model should
# solve most -- giving a meaningful quality/cost comparison.
# ---------------------------------------------------------------------------
HARD_TASKS = [
    dict(
        id="min_window", difficulty="expert", entry="min_window",
        prompt="Write a function min_window(s, t) that returns the smallest substring of s containing every character of t (including multiplicities). If no such window exists, return ''. Aim for linear time using a sliding window.",
        tests=(
            "assert min_window('ADOBECODEBANC','ABC')=='BANC'\n"
            "assert min_window('a','a')=='a'\n"
            "assert min_window('a','aa')==''\n"
            "assert min_window('aaflslflsassekgoodbad','goodbad')=='goodbad'\n"
            "assert min_window('','a')==''"
        ),
    ),
    dict(
        id="calculator", difficulty="expert", entry="calculate",
        prompt="Write a function calculate(s) that evaluates a mathematical expression string s containing non-negative integers and the operators +, -, *, / (integer division truncating toward zero), plus spaces. Respect standard operator precedence. No parentheses. Example: '3+2*2' -> 7.",
        tests=(
            "assert calculate('3+2*2')==7\n"
            "assert calculate(' 3/2 ')==1\n"
            "assert calculate(' 3+5 / 2 ')==5\n"
            "assert calculate('14-3/2')==13\n"
            "assert calculate('100')==100"
        ),
    ),
    dict(
        id="course_schedule", difficulty="expert", entry="can_finish",
        prompt="Write a function can_finish(num_courses, prerequisites) that returns True if you can finish all courses given prerequisite pairs [a, b] meaning b must be taken before a. This is equivalent to detecting whether a directed graph has no cycle.",
        tests=(
            "assert can_finish(2,[[1,0]])==True\n"
            "assert can_finish(2,[[1,0],[0,1]])==False\n"
            "assert can_finish(4,[[1,0],[2,1],[3,2]])==True\n"
            "assert can_finish(3,[[0,1],[1,2],[2,0]])==False\n"
            "assert can_finish(1,[])==True"
        ),
    ),
    dict(
        id="coin_change", difficulty="expert", entry="coin_change",
        prompt="Write a function coin_change(coins, amount) that returns the fewest number of coins needed to make up 'amount' using unlimited coins of the given denominations, or -1 if it cannot be made. Use dynamic programming.",
        tests=(
            "assert coin_change([1,2,5],11)==3\n"
            "assert coin_change([2],3)==-1\n"
            "assert coin_change([1],0)==0\n"
            "assert coin_change([1,5,10,25],63)==6\n"
            "assert coin_change([186,419,83,408],6249)==20"
        ),
    ),
    dict(
        id="trap_rain", difficulty="expert", entry="trap",
        prompt="Write a function trap(height) that, given a list of non-negative integers representing an elevation map where the width of each bar is 1, returns how many units of rain water can be trapped after raining.",
        tests=(
            "assert trap([0,1,0,2,1,0,1,3,2,1,2,1])==6\n"
            "assert trap([4,2,0,3,2,5])==9\n"
            "assert trap([])==0\n"
            "assert trap([1,2,3])==0\n"
            "assert trap([3,0,0,2,0,4])==10"
        ),
    ),
    dict(
        id="lru_cache", difficulty="expert", entry="run_lru",
        prompt="Implement an LRU (least-recently-used) cache and expose a function run_lru(capacity, ops) that replays operations. Each op is ('put', key, value) or ('get', key). run_lru returns the list of results of every 'get' op, where a miss returns -1. put and get must both count as a use (recency update).",
        tests=(
            "assert run_lru(2,[('put',1,1),('put',2,2),('get',1),('put',3,3),('get',2),('put',4,4),('get',1),('get',3),('get',4)])==[1,-1,-1,3,4]\n"
            "assert run_lru(1,[('put',1,1),('put',2,2),('get',1),('get',2)])==[-1,2]\n"
            "assert run_lru(2,[('get',0)])==[-1]"
        ),
    ),
    dict(
        id="word_ladder", difficulty="expert", entry="ladder_length",
        prompt="Write a function ladder_length(begin, end, word_list) that returns the number of words in the shortest transformation sequence from begin to end, changing one letter at a time, where every intermediate word must be in word_list. Return 0 if no such sequence exists. The length counts both begin and end words. Use breadth-first search.",
        tests=(
            "assert ladder_length('hit','cog',['hot','dot','dog','lot','log','cog'])==5\n"
            "assert ladder_length('hit','cog',['hot','dot','dog','lot','log'])==0\n"
            "assert ladder_length('a','c',['a','b','c'])==2"
        ),
    ),
    dict(
        id="max_subarray_product", difficulty="expert", entry="max_product",
        prompt="Write a function max_product(nums) that returns the largest product of any contiguous non-empty subarray of the integer list nums. Handle negative numbers and zeros correctly in linear time.",
        tests=(
            "assert max_product([2,3,-2,4])==6\n"
            "assert max_product([-2,0,-1])==0\n"
            "assert max_product([-2,3,-4])==24\n"
            "assert max_product([0,2])==2\n"
            "assert max_product([-2])==-2"
        ),
    ),
]

# ---------------------------------------------------------------------------
# Additional problems across difficulties to enrich the benchmark suite.
# ---------------------------------------------------------------------------
MORE_TASKS = [
    dict(
        id="climb_stairs", difficulty="medium", entry="climb_stairs",
        prompt="Write a function climb_stairs(n) that returns the number of distinct ways to climb a staircase of n steps taking 1 or 2 steps at a time.",
        tests="assert climb_stairs(2)==2\nassert climb_stairs(3)==3\nassert climb_stairs(5)==8\nassert climb_stairs(1)==1",
    ),
    dict(
        id="gcd", difficulty="medium", entry="gcd",
        prompt="Write a function gcd(a, b) that returns the greatest common divisor of non-negative integers a and b.",
        tests="assert gcd(12,18)==6\nassert gcd(7,1)==1\nassert gcd(0,5)==5\nassert gcd(100,10)==10",
    ),
    dict(
        id="roman_to_int", difficulty="medium", entry="roman_to_int",
        prompt="Write a function roman_to_int(s) that converts a Roman numeral string s (I, V, X, L, C, D, M) to its integer value.",
        tests="assert roman_to_int('III')==3\nassert roman_to_int('IV')==4\nassert roman_to_int('IX')==9\nassert roman_to_int('LVIII')==58\nassert roman_to_int('MCMXCIV')==1994",
    ),
    dict(
        id="binary_search", difficulty="medium", entry="binary_search",
        prompt="Write a function binary_search(arr, target) that returns the index of target in the sorted list arr, or -1 if it is not present. Use binary search.",
        tests="assert binary_search([1,2,3,4,5],3)==2\nassert binary_search([1,3,5,7],7)==3\nassert binary_search([1,3,5],2)==-1\nassert binary_search([],1)==-1",
    ),
    dict(
        id="kadane", difficulty="hard", entry="max_subarray",
        prompt="Write a function max_subarray(nums) that returns the largest sum of any contiguous non-empty subarray of the integer list nums (Kadane's algorithm).",
        tests="assert max_subarray([-2,1,-3,4,-1,2,1,-5,4])==6\nassert max_subarray([1])==1\nassert max_subarray([-1,-2])==-1\nassert max_subarray([5,4,-1,7,8])==23",
    ),
    dict(
        id="rotate_matrix", difficulty="hard", entry="rotate",
        prompt="Write a function rotate(matrix) that rotates an n x n matrix (list of lists) 90 degrees clockwise and returns the resulting matrix.",
        tests="assert rotate([[1,2],[3,4]])==[[3,1],[4,2]]\nassert rotate([[1,2,3],[4,5,6],[7,8,9]])==[[7,4,1],[8,5,2],[9,6,3]]",
    ),
    dict(
        id="spiral_order", difficulty="hard", entry="spiral_order",
        prompt="Write a function spiral_order(matrix) that returns all elements of the matrix (list of lists) in clockwise spiral order as a flat list.",
        tests="assert spiral_order([[1,2,3],[4,5,6],[7,8,9]])==[1,2,3,6,9,8,7,4,5]\nassert spiral_order([[1,2],[3,4]])==[1,2,4,3]\nassert spiral_order([[1]])==[1]",
    ),
    dict(
        id="longest_palindrome", difficulty="hard", entry="longest_palindrome",
        prompt="Write a function longest_palindrome(s) that returns the LENGTH of the longest palindromic substring of s.",
        tests="assert longest_palindrome('babad')==3\nassert longest_palindrome('cbbd')==2\nassert longest_palindrome('a')==1\nassert longest_palindrome('ac')==1\nassert longest_palindrome('forgeeksskeegfor')==10",
    ),
    dict(
        id="decode_ways", difficulty="expert", entry="num_decodings",
        prompt="Write a function num_decodings(s) that returns the number of ways to decode a digit string s where '1'->A, ..., '26'->Z. Leading zeros make a grouping invalid. Use dynamic programming.",
        tests="assert num_decodings('12')==2\nassert num_decodings('226')==3\nassert num_decodings('0')==0\nassert num_decodings('06')==0\nassert num_decodings('11106')==2",
    ),
    dict(
        id="unique_paths", difficulty="expert", entry="unique_paths",
        prompt="Write a function unique_paths(m, n) that returns the number of distinct paths a robot can take from the top-left to the bottom-right of an m x n grid, moving only right or down. Use dynamic programming.",
        tests="assert unique_paths(3,7)==28\nassert unique_paths(3,2)==3\nassert unique_paths(1,1)==1\nassert unique_paths(3,3)==6",
    ),
    dict(
        id="num_islands", difficulty="expert", entry="num_islands",
        prompt="Write a function num_islands(grid) that counts the number of islands in a 2D grid of '1' (land) and '0' (water). An island is formed by connecting adjacent lands horizontally or vertically.",
        tests="assert num_islands([['1','1','0'],['0','1','0'],['0','0','1']])==2\nassert num_islands([['1','1','1'],['0','1','0'],['1','1','1']])==1\nassert num_islands([['0','0'],['0','0']])==0",
    ),
    dict(
        id="wildcard_match", difficulty="expert", entry="is_match",
        prompt="Write a function is_match(s, p) implementing wildcard pattern matching where '?' matches any single character and '*' matches any sequence (including empty). The match must cover the ENTIRE string s.",
        tests="assert is_match('aa','a')==False\nassert is_match('aa','*')==True\nassert is_match('cb','?a')==False\nassert is_match('adceb','*a*b')==True\nassert is_match('acdcb','a*c?b')==False",
    ),
]

# ---------------------------------------------------------------------------
# BRUTAL problems: classic "Hard" algorithmic challenges with many edge cases
# and non-obvious algorithms. Small local models are expected to fail several
# of these; strong models should solve most. Used to create clear separation
# between model classes in the benchmark.
# ---------------------------------------------------------------------------
BRUTAL_TASKS = [
    dict(
        id="regex_match", difficulty="brutal", entry="is_match_regex",
        prompt="Write a function is_match_regex(s, p) implementing regular-expression matching where '.' matches any single character and '*' matches zero or more of the PRECEDING element. The match must cover the ENTIRE string s.",
        tests=(
            "assert is_match_regex('aa','a')==False\n"
            "assert is_match_regex('aa','a*')==True\n"
            "assert is_match_regex('ab','.*')==True\n"
            "assert is_match_regex('aab','c*a*b')==True\n"
            "assert is_match_regex('mississippi','mis*is*p*.')==False"
        ),
    ),
    dict(
        id="longest_valid_parens", difficulty="brutal", entry="longest_valid_parens",
        prompt="Write a function longest_valid_parens(s) that returns the length of the longest valid (well-formed) parentheses substring of s (s contains only '(' and ')').",
        tests=(
            "assert longest_valid_parens('(()')==2\n"
            "assert longest_valid_parens(')()())')==4\n"
            "assert longest_valid_parens('')==0\n"
            "assert longest_valid_parens('()(()')==2\n"
            "assert longest_valid_parens('()(())')==6"
        ),
    ),
    dict(
        id="largest_rectangle", difficulty="brutal", entry="largest_rectangle",
        prompt="Write a function largest_rectangle(heights) that returns the area of the largest rectangle that fits under a histogram whose bar heights are given by the list 'heights'. Aim for linear time using a stack.",
        tests=(
            "assert largest_rectangle([2,1,5,6,2,3])==10\n"
            "assert largest_rectangle([2,4])==4\n"
            "assert largest_rectangle([1,1])==2\n"
            "assert largest_rectangle([0])==0\n"
            "assert largest_rectangle([6,2,5,4,5,1,6])==12"
        ),
    ),
    dict(
        id="min_jumps", difficulty="brutal", entry="min_jumps",
        prompt="Write a function min_jumps(nums) that returns the minimum number of jumps to reach the last index, where nums[i] is the maximum jump length from index i. Assume the last index is always reachable.",
        tests=(
            "assert min_jumps([2,3,1,1,4])==2\n"
            "assert min_jumps([2,3,0,1,4])==2\n"
            "assert min_jumps([0])==0\n"
            "assert min_jumps([1,1,1,1])==3"
        ),
    ),
    dict(
        id="candy", difficulty="brutal", entry="candy",
        prompt="Write a function candy(ratings) that distributes candies to children in a line so each child gets at least one candy and any child with a higher rating than an immediate neighbor gets more candies than that neighbor. Return the minimum total candies.",
        tests=(
            "assert candy([1,0,2])==5\n"
            "assert candy([1,2,2])==4\n"
            "assert candy([1,3,2,2,1])==7\n"
            "assert candy([1,2,87,87,87,2,1])==13"
        ),
    ),
    dict(
        id="sliding_window_max", difficulty="brutal", entry="max_sliding_window",
        prompt="Write a function max_sliding_window(nums, k) that returns a list of the maximum value in every contiguous window of size k as the window slides across nums. Aim for linear time using a deque.",
        tests=(
            "assert max_sliding_window([1,3,-1,-3,5,3,6,7],3)==[3,3,5,5,6,7]\n"
            "assert max_sliding_window([1],1)==[1]\n"
            "assert max_sliding_window([9,11],2)==[11]\n"
            "assert max_sliding_window([4,-2],2)==[4]"
        ),
    ),
    dict(
        id="n_queens", difficulty="brutal", entry="count_n_queens",
        prompt="Write a function count_n_queens(n) that returns the number of distinct solutions to the N-Queens puzzle: placing n queens on an n x n board so that no two attack each other.",
        tests=(
            "assert count_n_queens(1)==1\n"
            "assert count_n_queens(4)==2\n"
            "assert count_n_queens(5)==10\n"
            "assert count_n_queens(6)==4\n"
            "assert count_n_queens(8)==92"
        ),
    ),
    dict(
        id="calc_paren", difficulty="brutal", entry="calc_paren",
        prompt="Write a function calc_paren(s) that evaluates a string expression containing non-negative integers, '+', '-', parentheses '(' ')', and spaces, respecting parentheses. Example: '(1+(4+5+2)-3)+(6+8)' -> 23.",
        tests=(
            "assert calc_paren('1 + 1')==2\n"
            "assert calc_paren(' 2-1 + 2 ')==3\n"
            "assert calc_paren('(1+(4+5+2)-3)+(6+8)')==23\n"
            "assert calc_paren('2-(5-6)')==3\n"
            "assert calc_paren('- (3 + (4 + 5))')==-12"
        ),
    ),
    dict(
        id="lis", difficulty="brutal", entry="length_of_lis",
        prompt="Write a function length_of_lis(nums) that returns the length of the longest strictly increasing subsequence of the list nums. Aim for O(n log n).",
        tests=(
            "assert length_of_lis([10,9,2,5,3,7,101,18])==4\n"
            "assert length_of_lis([0,1,0,3,2,3])==4\n"
            "assert length_of_lis([7,7,7,7])==1\n"
            "assert length_of_lis([])==0"
        ),
    ),
    dict(
        id="burst_balloons", difficulty="brutal", entry="max_coins",
        prompt="Write a function max_coins(nums) that returns the maximum coins obtainable by bursting all balloons, where bursting balloon i gives nums[left]*nums[i]*nums[right] coins (out-of-range neighbors count as 1). Use interval dynamic programming.",
        tests=(
            "assert max_coins([3,1,5,8])==167\n"
            "assert max_coins([1,5])==10\n"
            "assert max_coins([1])==1\n"
            "assert max_coins([7])==7"
        ),
    ),
    dict(
        id="decode_string", difficulty="brutal", entry="decode_string",
        prompt="Write a function decode_string(s) that decodes an encoded string with the rule k[encoded] meaning the bracketed content repeated k times, supporting nesting. Example: '3[a2[c]]' -> 'accaccacc'.",
        tests=(
            "assert decode_string('3[a]2[bc]')=='aaabcbc'\n"
            "assert decode_string('3[a2[c]]')=='accaccacc'\n"
            "assert decode_string('2[abc]3[cd]ef')=='abcabccdcdcdef'\n"
            "assert decode_string('abc')=='abc'"
        ),
    ),
    dict(
        id="partition_equal", difficulty="brutal", entry="can_partition",
        prompt="Write a function can_partition(nums) that returns True if the list of positive integers can be split into two subsets with equal sum, else False. Use dynamic programming (subset sum).",
        tests=(
            "assert can_partition([1,5,11,5])==True\n"
            "assert can_partition([1,2,3,5])==False\n"
            "assert can_partition([2,2,2,2])==True\n"
            "assert can_partition([1,2,5])==False"
        ),
    ),
]

TASKS = TASKS + HARD_TASKS + MORE_TASKS + BRUTAL_TASKS

