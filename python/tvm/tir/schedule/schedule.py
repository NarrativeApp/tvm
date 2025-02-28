# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""The TensorIR schedule class"""
from typing import Dict, List, Optional, Union

from tvm._ffi import register_object as _register_object
from tvm.error import TVMError, register_error
from tvm.ir import IRModule, PrimExpr
from tvm.runtime import Object
from tvm.tir import Block, For, IntImm, PrimFunc

from . import _ffi_api
from .state import ScheduleState, StmtSRef, _parse_debug_mask, _parse_mod
from .trace import Trace
from ._type_checker import type_checked


@register_error
class ScheduleError(TVMError):
    """Error that happens during TensorIR scheduling."""


@_register_object("tir.LoopRV")
class LoopRV(Object):
    """A random variable that refers to a loop"""

    def __init__(self) -> None:
        """Construct a new LoopRV."""
        self.__init_handle_by_constructor__(
            _ffi_api.LoopRV  # type: ignore # pylint: disable=no-member
        )


@_register_object("tir.BlockRV")
class BlockRV(Object):
    """A random variable that refers to a block"""

    def __init__(self) -> None:
        """Construct a new BlockRV."""
        self.__init_handle_by_constructor__(
            _ffi_api.BlockRV  # type: ignore # pylint: disable=no-member
        )


# It is a workaround for mypy: https://github.com/python/mypy/issues/7866#issuecomment-549454370
# This feature is not supported until python 3.10:
# https://docs.python.org/3.10/whatsnew/3.10.html#pep-613-typealias
ExprRV = Union[PrimExpr]  # A random variable that evaluates to an integer

RAND_VAR_TYPE = Union[ExprRV, BlockRV, LoopRV]  # pylint: disable=invalid-name

# Update to `Literal["detail", "fast", "none"]` once upgraded to python3.8
_ERROR_RENDER_LEVEL: Dict[str, int] = {
    "detail": 0,
    "fast": 1,
    "none": 2,
}


def _parse_error_render_level(error_render_level: str) -> int:
    if error_render_level not in _ERROR_RENDER_LEVEL:
        raise ValueError(
            'error_render_level can be "detail", "fast", or "none", but got: '
            + f"{error_render_level}"
        )
    return _ERROR_RENDER_LEVEL.get(error_render_level)


def _parse_seed(seed: Optional[int]) -> int:
    if seed is None:
        return -1
    if not isinstance(seed, int):
        raise TypeError(f"Expected `seed` to be int or None, but gets: {seed}")
    if seed < 1 or seed > 2147483647:
        raise ValueError(f"seed must be in the range [1, 2147483647], but gets: {seed}")
    return seed


@_register_object("tir.Schedule")
class Schedule(Object):
    """The user-facing schedule class

    A schedule is a set of transformations that change the order of computation but
    preserve the semantics of computation. Some example of schedules:
    1) Split a loop into two;
    2) Reorder two loops;
    3) Inline the computation of a specific buffer into its consumer

    The schedule class stores auxiliary information to schedule correctly and efficiently.

    Link to tutorial: https://tvm.apache.org/docs/tutorials/language/schedule_primitives.html
    """

    @type_checked
    def __init__(
        self,
        mod: Union[PrimFunc, IRModule],
        *,
        seed: Optional[int] = None,
        debug_mask: Union[str, int] = "none",
        error_render_level: str = "detail",
    ) -> None:
        """Construct a TensorIR schedule class from an IRModule

        Parameters
        ----------
        mod : Union[PrimFunc, IRModule]
            The IRModule or PrimFunc to be scheduled
        seed: Optional[int]
            The seed value for schedule's random state
            Note that None and -1 means use device random, otherwise only integer between 1 and
            2147483647 is allowed.
        debug_mask : Union[str, int]
            Do extra correctness checking after the class creation and each time
            after calling the Replace method.
            Possible choices of `debug_mask`:
            1) "all" - Turn on all the checks
            2) "none" - Turn off all the checks
            3) An integer - Turn on checks according to the bitmasks provided in ScheduleDebugMask
        error_render_level : str = "detail"
            The level of error rendering. Choices: "detail", "fast", "none".
            - "detail": Render a detailed error message, with the TIR and error locations printed
            - "fast: Show a simple error message without rendering or string manipulation
            - "none": Do not show any error message.

        Note
        ----
        The checks performed includes:
        1) VerifySRefTree
        2) VerifyCachedFlags
        """
        # call the constructor
        self.__init_handle_by_constructor__(
            _ffi_api.TracedSchedule,  # type: ignore # pylint: disable=no-member
            _parse_mod(mod),
            _parse_seed(seed),
            _parse_debug_mask(debug_mask),
            _parse_error_render_level(error_render_level),
        )

    @staticmethod
    def _create_non_traced(
        mod: Union[PrimFunc, IRModule],
        *,
        seed: Optional[int] = None,
        debug_mask: Union[str, int] = "none",
        error_render_level: str = "detail",
    ) -> "Schedule":
        """Construct a non-traced TensorIR schedule class from an IRModule."""
        return _ffi_api.ConcreteSchedule(  # type: ignore # pylint: disable=no-member
            _parse_mod(mod),
            _parse_seed(seed),
            _parse_debug_mask(debug_mask),
            _parse_error_render_level(error_render_level),
        )

    ########## Utilities ##########

    @property
    def mod(self) -> IRModule:
        """Returns the AST of the module being scheduled"""
        return _ffi_api.ScheduleGetMod(self)  # type: ignore # pylint: disable=no-member

    @property
    def state(self) -> ScheduleState:
        """Returns the ScheduleState in the current schedule class"""
        return _ffi_api.ScheduleGetState(self)  # type: ignore # pylint: disable=no-member

    @property
    def trace(self) -> Optional[Trace]:
        """Returns the internally maintained trace of scheduling program execution"""
        return _ffi_api.ScheduleGetTrace(self)  # type: ignore # pylint: disable=no-member

    def copy(self) -> "Schedule":
        """Returns a copy of the schedule, including both the state and the symbol table,
        * guaranteeing that
        * 1) SRef tree is completely reconstructed;
        * 2) The IRModule being scheduled is untouched;
        * 3) All the random variables are valid in the copy, pointing to the corresponding sref
        * reconstructed

        Returns
        -------
        copy : Schedule
            A new copy of the schedule
        """
        return _ffi_api.ScheduleCopy(self)  # type: ignore # pylint: disable=no-member

    @type_checked
    def seed(self, seed: int) -> None:
        """Seed the randomness

        Parameters
        ----------
        seed : int
            The new random seed, -1 if use device random, otherwise non-negative
        """
        return _ffi_api.ScheduleSeed(self, seed)  # type: ignore # pylint: disable=no-member

    def fork_seed(self) -> int:
        """Returns a forked random state as seed for new schedules

        Returns
        -------
        seed : int
            The forked random state, not the same as the current random state
        """
        return _ffi_api.ScheduleForkSeed(self)  # type: ignore # pylint: disable=no-member

    @type_checked
    def show(self, rand_var: RAND_VAR_TYPE) -> str:
        """Returns a string representation of the value that the random variable evaluates to

        Parameters
        ----------
        rand_var : Union[ExprRV, BlockRV, LoopRV]
            The random variable to be evaluated

        Returns
        -------
        str_repr : str
            The string representation
        """
        return str(self.get(rand_var))

    ########## Lookup ##########

    @type_checked
    def get(
        self,
        rand_var_or_sref: Union[RAND_VAR_TYPE, StmtSRef],
    ) -> Optional[Union[int, Block, For]]:
        """Returns:
        - the corresponding Block that a BlockRV evaluates to;
        - the corresponding For that a LoopRV evaluates to;
        - the corresponding integer that a ExprRV evaluates to;
        - the corresponding Block that a block sref points to;
        - the corresponding For that a loop sref points to;

        Parameters
        ----------
        rand_var_or_sref : Union[ExprRV, BlockRV, LoopRV, StmtSRef]
            The random variable / sref to be evaluated

        Returns
        -------
        result : Optional[Union[int, Block, For]]
            The corresponding result
        """
        if isinstance(rand_var_or_sref, StmtSRef):
            return rand_var_or_sref.stmt
        result = _ffi_api.ScheduleGet(self, rand_var_or_sref)  # type: ignore # pylint: disable=no-member
        if isinstance(result, IntImm):
            result = result.value
        return result

    @type_checked
    def get_sref(self, rand_var_or_stmt: Union[BlockRV, LoopRV, Block, For]) -> Optional[StmtSRef]:
        """Returns the corresponding sref to the given
        1) LoopRV
        2) BlockRV
        3) Block
        4) For

        Parameters
        ----------
        rand_var_or_stmt : Union[BlockRV, LoopRV, Block, For]
            The random variable / sref to be evaluated

        Returns
        -------
        result : Optional[StmtSRef]
            The corresponding result
        """
        return _ffi_api.ScheduleGetSRef(  # type: ignore # pylint: disable=no-member
            self, rand_var_or_stmt
        )

    @type_checked
    def remove_rv(self, rand_var: RAND_VAR_TYPE) -> None:
        """Remove a random variable from the symbol table

        Parameters
        ----------
        rand_var : Union[BlockRV, LoopRV, ExprRV]
            The random variable to be removed
        """
        return _ffi_api.ScheduleRemoveRV(self, rand_var)  # type: ignore # pylint: disable=no-member

    ########## Schedule: Sampling ##########

    @type_checked
    def sample_categorical(
        self,
        candidates: List[int],
        probs: List[float],
        decision: Optional[int] = None,
    ) -> ExprRV:
        """Sample an integer given the probability distribution

        Parameters
        ----------
        candidates : List[int]
            The candidates to be sampled from
        probs : List[float]
            The probability of each candidate
        decision : Optional[int]
            The sampling decision, if any

        Returns
        -------
        result : ExprRV
            The random variable sampled from candidates
        """
        return _ffi_api.ScheduleSampleCategorical(  # type: ignore # pylint: disable=no-member
            self,
            candidates,
            probs,
            decision,
        )

    @type_checked
    def sample_perfect_tile(
        self,
        loop: LoopRV,
        n: int,
        max_innermost_factor: int = 16,
        decision: Optional[List[int]] = None,
    ) -> List[ExprRV]:
        """Sample the factors to perfect tile a specific loop

        Parameters
        ----------
        loop : LoopRV
            The loop to be tiled
        n : int
            The number of tiles to be sampled
        max_innermost_factor : int
            The maximum tile size allowed to be sampled in the innermost loop
        decision: Optional[List[int]]
            The sampling decision, if any

        Returns
        -------
        result : List[ExprRV]
            A list of length `n`, the random perfect tile sizes sampled
        """
        return list(
            _ffi_api.ScheduleSamplePerfectTile(  # type: ignore  # pylint: disable=no-member
                self,
                loop,
                n,
                max_innermost_factor,
                decision,
            )
        )

    ########## Schedule: Get blocks & loops ##########
    @type_checked
    def get_block(
        self,
        name: str,
        func_name: str = "main",
    ) -> BlockRV:
        """Retrieve a block in a specific function with its name

        Parameters
        ----------
        name : str
            The name of the block
        func_name : str = "main"
            The name of the function

        Returns
        -------
        block : BlockRV
            The block retrieved
            IndexError is raised if 0 or multiple blocks exist with the specific name.
        """
        return _ffi_api.ScheduleGetBlock(  # type: ignore # pylint: disable=no-member
            self,
            name,
            func_name,
        )

    @type_checked
    def get_loops(self, block: BlockRV) -> List[LoopRV]:
        """Get the parent loops of the block in its scope, from outer to inner

        Parameters
        ----------
        block : BlockRV
            The query block

        Returns
        -------
        loops : List[LoopRV]
            A list of loops above the given block in its scope, from outer to inner
        """
        return list(_ffi_api.ScheduleGetLoops(self, block))  # type: ignore # pylint: disable=no-member

    @type_checked
    def get_child_blocks(self, block_or_loop: Union[BlockRV, LoopRV]) -> List[BlockRV]:
        """Get the leaf blocks of a specific block/loop

        Parameters
        ----------
        block_or_loop : Union[BlockRV, LoopRV]
            The query block/loop

        Returns
        -------
        blocks : List[LoopRV]
            A list of leaf blocks inside a specific block/loop
        """
        return list(_ffi_api.ScheduleGetChildBlocks(self, block_or_loop))  # type: ignore # pylint: disable=no-member

    @type_checked
    def get_producers(self, block: BlockRV) -> List[BlockRV]:
        """Get the producers of a specific block

        Parameters
        ----------
        block : BlockRV
            The block in the query

        Returns
        -------
        producers : List[BlockRV]
            A list of producers of the given block
        """
        return list(_ffi_api.ScheduleGetProducers(self, block))  # type: ignore # pylint: disable=no-member

    @type_checked
    def get_consumers(self, block: BlockRV) -> List[BlockRV]:
        """Get the consumers of a specific block

        Parameters
        ----------
        block : BlockRV
            The block in the query

        Returns
        -------
        consumers : List[BlockRV]
            A list of consumers of the given block
        """
        return list(_ffi_api.ScheduleGetConsumers(self, block))  # type: ignore # pylint: disable=no-member

    ########## Schedule: Transform loops ##########
    @type_checked
    def fuse(self, *loops: List[LoopRV]) -> LoopRV:
        """Fuse a list of consecutive loops into one. It requires:
        1) The loops can't have annotations or thread bindings.
        2) The (i+1)-th loop must be the only child of the i-th loop.
        3) All loops must start with 0.
        4) The domain of a loop to be fused cannot depend on another loop to be fused.

        Parameters
        ----------
        *loops : List[LoopRV]
            The loops to be fused

        Returns
        -------
        fused_loop : LoopRV
            The new loop after fusion

        Examples
        --------

        Before applying fuse, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_fuse(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0

        Create the schedule and do fuse:

        .. code-block:: python

            sch = tir.Schedule(before_fuse)
            i, j = sch.get_loops(sch.get_block("B"))
            sch.fuse(i, j)
            print(sch.mod["main"].script())

        After applying fuse, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_fuse(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                # the 2 loops are fused into 1
                for i_j_fused in T.serial(0, 16384):
                    with T.block("B"):
                        vi = T.axis.S(128, T.floordiv(i_j_fused, 128))
                        vj = T.axis.S(128, T.floormod(i_j_fused, 128))
                        B[vi, vj] = A[vi, vj] * 2.0

        """
        return _ffi_api.ScheduleFuse(self, loops)  # type: ignore # pylint: disable=no-member

    @type_checked
    def split(
        self,
        loop: LoopRV,
        factors: List[Union[int, ExprRV, None]],
    ) -> List[LoopRV]:
        """Split a loop into a list of consecutive loops. It requires:
        1) The loop can't have annotation or thread binding.
        2) The loop must start with 0.
        Predicates may be added to ensure the total loop numbers keeps unchanged.
        In `factors`, at most one of the factors can be None,
        which will be automatically inferred.

        Parameters
        ----------
        loop : LoopRV
            The loop to be split

        factors: List[Union[int, ExprRV, None]]
            The splitting factors
            Potential inputs are:
            - None
            - ExprRV
            - Non-negative constant integers

        Returns
        -------
        split_loops : List[LoopRV]
            The new loops after split

        Examples
        --------

        Before split, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_split(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B") as [vi, vj]:
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0

        Create the schedule and do split:

        .. code-block:: python

            sch = tir.Schedule(before_split)
            i, j = sch.get_loops(sch.get_block("B"))
            sch.split(i, factors=[2, 64])
            print(sch.mod["main"].script())

        After applying split, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_split(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                # the original loop is split into 2 loops
                for i0, i1, j in T.grid(2, 64, 128):
                    with T.block("B"):
                        vi = T.axis.S(128, i0 * 64 + i1)
                        vj = T.axis.S(128, j)
                        B[vi, vj] = A[vi, vj] * 2.0

        """
        # it will be checked later in C++ implementation
        # that there is at most one None in `factors`
        return list(_ffi_api.ScheduleSplit(self, loop, factors))  # type: ignore # pylint: disable=no-member

    @type_checked
    def reorder(self, *ordered_loops: List[LoopRV]) -> None:
        """
        Reorder a list of loops. It doesn't require the loops to be consecutive.
        It requires:
        1) The loops are in the same chain. That means: the loops can be ordered to [l_1, l_2, ... ,
        l_n] where l_i is an ancestor of l_{i+1} and there are only single-branch loops between
        l_1 and l_n (which also indicates they are under the same scope).
        2) After reordering, the domain of an outer loop cannot depend on any of the inner loops.
        3) For every block under the loop nests, its block binding must be affine, and the block
        variables must be either data parallel or reduction.
        4) No duplicated loops are allowed in the arguments.

        Parameters
        ----------
        *ordered_loops : List[LoopRV]
            The loops in the new order

        Examples
        --------

        Before reorder, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_reorder(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0

        Create the schedule and do reorder:

        .. code-block:: python

            sch = tir.Schedule(before_reorder)
            i, j = sch.get_loops(sch.get_block("B"))
            sch.reorder(j, i)
            print(sch.mod["main"].script())

        After applying reorder, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_reorder(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                # Here j and i are reordered
                for j, i in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0

        """
        _ffi_api.ScheduleReorder(self, ordered_loops)  # type: ignore # pylint: disable=no-member

    ########## Schedule: Manipulate ForKind ##########

    @type_checked
    def parallel(self, loop: LoopRV) -> None:
        """Parallelize the input loop. It requires:
        1) The scope block that the loop is in should have stage-pipeline property
        2) All the blocks under the loop are complete blocks or reduction blocks, and have affine
        bindings
        3) For each block under the loop, the loop can only be contained in data-parallel block
        iters' bindings

        Parameters
        ----------
        loop : LoopRV
            The loop to be parallelized

        Examples
        --------

        Before parallel, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_parallel(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0

        Create the schedule and do parallel:

        .. code-block:: python

            sch = tir.Schedule(before_parallel)
            i, j = sch.get_loops(sch.get_block("B"))
            sch.parallel(i)

        After applying parallel, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_parallel(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i in T.parallel(0, 128):
                    for j in T.serial(0, 128):
                        with T.block("B"):
                            vi, vj = T.axis.remap("SS", [i, j])
                            B[vi, vj] = A[vi, vj] * 2.0

        """
        _ffi_api.ScheduleParallel(self, loop)  # type: ignore # pylint: disable=no-member

    @type_checked
    def vectorize(self, loop: LoopRV) -> None:
        """Vectorize the input loop. It requires:
        1) The scope block that the loop is in should have stage-pipeline property
        2) All the blocks under the loop are complete blocks or reduction blocks, and have affine
        bindings
        3) For each block under the loop, the loop can only be contained in data-parallel block
        iters' bindings

        Parameters
        ----------
        loop : LoopRV
            The loop to be vectorized

        Examples
        --------

        Before vectorize, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_vectorize(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0

        Create the schedule and do vectorize:

        .. code-block:: python

            sch = tir.Schedule(before_vectorize)
            i, j = sch.get_loops(sch.get_block("B"))
            sch.vectorize(j)

        After applying vectorize, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_vectorize(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i in T.serial(0, 128):
                    for j in T.vectorized(0, 128):
                        with T.block("B"):
                            vi, vj = T.axis.remap("SS", [i, j])
                            B[vi, vj] = A[vi, vj] * 2.0

        """
        _ffi_api.ScheduleVectorize(self, loop)  # type: ignore # pylint: disable=no-member

    @type_checked
    def bind(self, loop: LoopRV, thread_axis: str) -> None:
        """Bind the input loop to the given thread axis. It requires:
        1) The scope block that the loop is in should have stage-pipeline property
        2) All the blocks under the loop are complete blocks or reduction blocks, and have affine
        bindings
        3) For each block under the loop, if the thread axis starts with "threadIdx`, the loop can
        only be contained in data-parallel block iter and reduction block iters' bindings. Otherwise
        the loop can only be contained in data-parallel block iters' bindings

        Parameters
        ----------
        loop : LoopRV
            The loop to be bound to the thread axis
        thread_axis : str
            The thread axis to be bound to the loop. Possible candidates:
            - blockIdx.x/y/z
            - threadIdx.x/y/z
            - vthread.x/y/z
            - vthread (It is a legacy behavior that will be deprecated. Please use `vthread.x/y/z`
            instead.)

        Examples
        --------

        Before bind, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_bind(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0

        Create the schedule and do bind:

        .. code-block:: python

            sch = tir.Schedule(before_bind)
            i, j = sch.get_loops(sch.get_block("B"))
            sch.bind(i, "blockIdx.x")
            sch.bind(j, "threadIdx.x")

        After applying bind, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_bind(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i in T.thread_binding(0, 128, thread = "blockIdx.x"):
                    for j in T.thread_binding(0, 128, thread = "threadIdx.x"):
                        with T.block("B"):
                            vi, vj = T.axis.remap("SS", [i, j])
                            B[vi, vj] = A[vi, vj] * 2.0

        """
        _ffi_api.ScheduleBind(self, loop, thread_axis)  # type: ignore # pylint: disable=no-member

    @type_checked
    def unroll(self, loop: LoopRV) -> None:
        """Unroll the input loop. It requires nothing

        Parameters
        ----------
        loop : LoopRV
            The loop to be unrolled

        Examples
        --------

        Before unroll, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_unroll(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0

        Create the schedule and do unroll:

        .. code-block:: python

            sch = tir.Schedule(before_unroll)
            i, j = sch.get_loops(sch.get_block("B"))
            sch.unroll(i)

        After applying unroll, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_unroll(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i in T.unroll(0, 128):
                    for j in T.serial(0, 128):
                        with T.block("B"):
                            vi, vj = T.axis.remap("SS", [i, j])
                            B[vi, vj] = A[vi, vj] * 2.0

        """
        _ffi_api.ScheduleUnroll(self, loop)  # type: ignore # pylint: disable=no-member

    ########## Schedule: Insert cache stages ##########

    @type_checked
    def cache_read(self, block: BlockRV, read_buffer_index: int, storage_scope: str) -> BlockRV:
        """Create a block that reads a buffer region into a read cache. It requires:

        1) There is at most one block who write the buffer in the scope.

        2) The scope block have stage-pipeline property.

        Parameters
        ----------
        block : BlockRV
            The consumer block of the target buffer.

        read_buffer_index: int
            The index of the buffer in block's read region.

        storage_scope: str
            The target storage scope.

        Returns
        -------
        cached_block : BlockRV
            The block of the cache stage

        Examples
        --------
        Before cache_read, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_cache_read(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0

        Create the schedule and cache_read:

        .. code-block:: python

            sch = tir.Schedule(before_cache_read)
            block_b = sch.get_block("B")
            sch.cache_read(block_b, 0, "local")
            print(sch.mod["main"].script())

        After applying cache_read, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_cache_read(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                A_local = T.alloc_buffer((128, 128), scope="local")
                for i, j in T.grid(128, 128):
                    with T.block("A_local"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        A_local[vi, vj] = A[vi, vj]
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A_local[vi, vj] * 2.0

        """
        return _ffi_api.ScheduleCacheRead(  # type: ignore # pylint: disable=no-member
            self, block, read_buffer_index, storage_scope
        )

    @type_checked
    def cache_write(self, block: BlockRV, write_buffer_index: int, storage_scope: str) -> BlockRV:
        """Create a block that reads a buffer region into a write cache. It requires:

        1) There is only one block who write the buffer in the scope.

        2) The scope block have stage-pipeline property.

        Parameters
        ----------
        block : BlockRV
            The producer block of the target buffer.

        write_buffer_index: int
            The index of the buffer in block's write region.

        storage_scope: str
            The target storage scope.


        Returns
        -------
        cached_block : BlockRV
            The block of the cache stage

        Examples
        --------
        Before cache_write, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_cache_write(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0

        Create the schedule and cache_write:

        .. code-block:: python

            sch = tir.Schedule(before_cache_write)
            block_b = sch.get_block("B")
            sch.cache_write(block_b, 0, "local")
            print(sch.mod["main"].script())

        After applying cache_write, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_cache_write(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.match_buffer(b, (128, 128))
                B_local = T.alloc_buffer((128, 128), scope="local")
                for i, j in T.grid(128, 128):
                    with T.block("A_local"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B_local[vi, vj] = A[vi, vj] * 2.0
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = B_local[vi, vj]

        """
        return _ffi_api.ScheduleCacheWrite(  # type: ignore # pylint: disable=no-member
            self, block, write_buffer_index, storage_scope
        )

    ########## Schedule: Compute location ##########

    @type_checked
    def compute_at(
        self,
        block: BlockRV,
        loop: LoopRV,
        preserve_unit_loops: bool = False,
    ) -> None:
        """Compute-At. Move a producer block under the specific loop, and regenerate the
        loops induced by the block so that the buffer region produced by the producer block could
        cover those regions consumed by its consumer blocks under the given loop. It requires:

        1) `block` and `loop` are under the same scope, `loop` is not the ancestor of `block`

        2) The scope block has stage-pipeline property

        3) The subtree of the scope block, where the given block is in, satisfies the compact
        dataflow condition. i.e. all the blocks in the scope block's subtree must be either
        complete block or reduction block

        4) The block is not an output block with regard to the scope block, i.e. the buffers written
        by the block are allocated under the scope block

        5) All the consumers of the block are under the given loop

        Parameters
        ----------
        block : BlockRV
            The block to be moved

        loop: LoopRV
            The loop where the block to be moved under

        preserve_unit_loops: bool
            Whether to keep the trivial loops whose extents are 1

        Examples
        --------

        Before compute-at, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_compute_at(a: T.handle, c: T.handle) -> None:
                A = T.match_buffer(a, (128, 128), "float32")
                B = T.alloc_buffer((128, 128), "float32")
                C = T.match_buffer(c, (128, 128), "float32")
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0
                for i, j in T.grid(128, 128):
                    with T.block("C"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        C[vi, vj] = B[vi, vj] + 1.0

        Create the schedule and do compute-at:

        .. code-block:: python

            sch = tir.Schedule(before_compute_at)
            block = sch.get_block("B")
            loop, _ = sch.get_loops(sch.get_block("C"))
            sch.compute_at(block, loop, preserve_unit_loops=False)
            print(sch.mod["main"].script())

        After applying compute-at, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_compute_at(a: T.handle, c: T.handle) -> None:
                A = T.match_buffer(a, (128, 128), "float32")
                B = T.alloc_buffer((128, 128), "float32")
                C = T.match_buffer(c, (128, 128), "float32")
                for i in T.serial(0, 128):
                    for j in T.serial(0, 128):
                        with T.block("B"):
                            vi, vj = T.axis.remap("SS", [i, j])
                            B[vi, vj] = A[vi, vj] * 2.0
                    for j in T.serial(0, 128):
                        with T.block("C"):
                            vi, vj = T.axis.remap("SS", [i, j])
                            C[vi, vj] = B[vi, vj] + 1.0

        """
        _ffi_api.ScheduleComputeAt(  # type: ignore # pylint: disable=no-member
            self,
            block,
            loop,
            preserve_unit_loops,
        )

    @type_checked
    def reverse_compute_at(
        self,
        block: BlockRV,
        loop: LoopRV,
        preserve_unit_loops: bool = False,
    ) -> None:
        """Reverse-Compute-At. Move a consumer block under the specific loop, and regenerate the
        loops induced by the block so that the buffer region consumed by the consumer block could
        cover those regions produced by its producer blocks under the given loop. It requires:

        1) `block` and `loop` are under the same scope, `loop` is not the ancestor of `block`

        2) The scope block has stage-pipeline property

        3) The subtree of the scope block, where the given block is in, satisfies the compact
        dataflow condition. i.e. all the blocks in the scope block's subtree must be either
        complete block or reduction block

        4) All the producers of the block are under the given loop

        Parameters
        ----------
        block : BlockRV
            The block to be moved

        loop: LoopRV
            The loop where the block to be moved under

        preserve_unit_loops: bool
            Whether to keep the trivial loops whose extents are 1

        Examples
        --------

        Before reverse-compute-at, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_reverse_compute_at(a: T.handle, c: T.handle) -> None:
                A = T.match_buffer(a, (128, 128), "float32")
                B = T.alloc_buffer((128, 128), "float32")
                C = T.match_buffer(c, (128, 128), "float32")
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0
                for i, j in T.grid(128, 128):
                    with T.block("C"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        C[vi, vj] = B[vi, vj] + 1.0

        Create the schedule and do reverse-compute-at:

        .. code-block:: python

            sch = tir.Schedule(before_reverse_compute_at)
            block = sch.get_block("C")
            loop, _ = sch.get_loops(sch.get_block("B"))
            sch.reverse_compute_at(block, loop, preserve_unit_loops=False)
            print(sch.mod["main"].script())

        After applying reverse-compute-at, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_reverse_compute_at(a: T.handle, c: T.handle) -> None:
                A = T.match_buffer(a, (128, 128), "float32")
                B = T.alloc_buffer((128, 128), "float32")
                C = T.match_buffer(c, (128, 128), "float32")
                for i in T.serial(0, 128):
                    for j in T.serial(0, 128):
                        with T.block("B"):
                            vi, vj = T.axis.remap("SS", [i, j])
                            B[vi, vj] = A[vi, vj] * 2.0
                    for j in T.serial(0, 128):
                        with T.block("C"):
                            vi, vj = T.axis.remap("SS", [i, j])
                            C[vi, vj] = B[vi, vj] + 1.0

        """
        _ffi_api.ScheduleReverseComputeAt(  # type: ignore # pylint: disable=no-member
            self,
            block,
            loop,
            preserve_unit_loops,
        )

    @type_checked
    def compute_inline(self, block: BlockRV) -> None:
        """Inline a block into its consumer(s). It requires:

        1) The block is a complete non-root block, which only produces one buffer

        2) The block must not be the only leaf in the scope.

        3) The body of the block must be a BufferStore statement in
           the form of, ``A[i, j, k, ...] = ...`` where the indices of
           the LHS are all distinct atomic variables, and no variables
           other than those indexing variables are allowed in the
           statement.

        Parameters
        ----------
        block : BlockRV
            The block to be inlined to its consumer(s)

        Examples
        --------

        Before compute-inline, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_inline(a: T.handle, c: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.alloc_buffer((128, 128))
                C = T.match_buffer(c, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0
                for i, j in T.grid(128, 128):
                    with T.block("C"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        C[vi, vj] = B[vi, vj] + 1.0

        Create the schedule and do compute-inline:

        .. code-block:: python

            sch = tir.Schedule(before_inline)
            sch.compute_inline(sch.get_block("B"))
            print(sch.mod["main"].script())

        After applying compute-inline, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_inline(a: T.handle, c: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                C = T.match_buffer(c, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("C"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        C[vi, vj] = A[vi, vj] * 2.0 + 1.0

        """
        _ffi_api.ScheduleComputeInline(self, block)  # type: ignore # pylint: disable=no-member

    @type_checked
    def reverse_compute_inline(self, block: BlockRV) -> None:
        """Inline a block into its only producer. It requires:

        1) The block is a complete non-root block, which only produces and consumes one buffer

        2) The block must not be the only leaf in the scope.

        3) The only producer of the block is a read-after-write producer and a
           complete non-root block

        4) The body of the block must be a BufferStore statement in the form of,
           ``B[f(i, j, k, ...)] = g(i, j, k, A[i, j, k, ...] ...)`` where the
           indices of each `BufferLoad` on the RHS are all distinct atomic
           variables, and no variables other than those indexing variables are
           allowed in the statement.

        Parameters
        ----------
        block : BlockRV
            The block to be inlined to its producer

        Examples
        --------

        Before reverse-compute-inline, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_inline(a: T.handle, c: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.alloc_buffer((128, 128))
                C = T.match_buffer(c, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0
                for i, j in T.grid(128, 128):
                    with T.block("C"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        C[vi, vj] = B[vi, vj] + 1.0

        Create the schedule and do reverse-compute-inline:

        .. code-block:: python

            sch = tir.Schedule(before_inline)
            sch.reverse_compute_inline(sch.get_block("C"))
            print(sch.mod["main"].script())

        After applying reverse-compute-inline, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_inline(a: T.handle, c: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                C = T.match_buffer(c, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("C"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        C[vi, vj] = A[vi, vj] * 2.0 + 1.0

        """
        _ffi_api.ScheduleReverseComputeInline(self, block)  # type: ignore # pylint: disable=no-member

    ########## Schedule: Reduction ##########

    @type_checked
    def decompose_reduction(self, block: BlockRV, loop: LoopRV) -> BlockRV:
        """Decompose a reduction block into two separate blocks.

        a) The init block, which is translated from the init statement of the reduction block;

        b) The update block, which is the original block without init statement.

        The init block is inserted right before the given loop.

        The schedule primitive requires:

        1) The input block is a reduction block.

        2) The input loop is the ancestor of the block.

        3) The input loop is not lower than all the loops related to reduce block var.

        Parameters
        ----------
        block : BlockRV
            The reduction block to be decomposed
        loop : LoopRV
            The loop above which the init block is inserted before.

        Returns
        -------
        init_block : BlockRV
            The init block

        Examples
        --------
        Before decompose-reduction, in TensorIR, the IR is:

        .. code-block:: python

            @tvm.script.tir
            def before_decompose(a: ty.handle, c: ty.handle) -> None:
                A = tir.match_buffer(a, [128, 128])
                B = tir.match_buffer(b, [128, 128])
                C = tir.match_buffer(c, [128, 128])
                for i, j, k in tir.grid(128, 128, 128):
                    with tir.block([128, 128, tir.reduce_axis(0, 128)], "C") as [vi, vj, vk]:
                        with tir.init():
                            C[vi, vj] = 0.0
                        C[vi, vj] = C[vi, vj] + A[vi, vk] * B[vj, vk]

        Create the schedule and do decompose-reduction with specified loop:

        .. code-block:: python

            sch = tir.Schedule(before_decompose)
            C = sch.get_block("C")
            i, j, k = sch.get_loops(C)
            sch.decompose_reduction(C, i)
            print(tvm.script.asscript(sch.mod["main"]))

        After applying decompose-reduction, the IR becomes:

        .. code-block:: python

            @tvm.script.tir
            def after_decompose(a: ty.handle, c: ty.handle) -> None:
                A = tir.match_buffer(a, [128, 128])
                B = tir.match_buffer(b, [128, 128])
                C = tir.match_buffer(c, [128, 128])
                for i in tir.serial(128):
                    for j in tir.serial(128):
                        with tir.block([128, 128]) as [vi, vj]:
                            C[vi, vj] = 0.0
                for i, j, k in tir.grid(128, 128, 128):
                    with tir.block([128, 128, tir.reduce_axis(0, 128)], "C") as [vi, vj, vk]:
                        C[vi, vj] = C[vi, vj] + A[vi, vk] * B[vj, vk]

        """
        return _ffi_api.ScheduleDecomposeReduction(self, block, loop)  # type: ignore # pylint: disable=no-member

    @type_checked
    def rfactor(self, loop: LoopRV, factor_axis: int) -> LoopRV:
        """Factorize an associative reduction block by the specified loop.

        An associative reduction cannot be parallelized directly,
        because it leads to potential race condition during accumulation.
        Alternatively, the reduction could be factorized on a loop with the following steps:
        - Step 1: evenly slice the reduction into `n` separate chunks, where `n` is the loop extent
        - Step 2: compute the chunks separately and write the result into `n` intermediate buffers;
        - Step 3: accumulate the `n` separate buffer into the result buffer.
        Note that the Step 2 above introduces opportunities for parallelization.

        RFactor is a schedule primitive that implements the transformation described above:
        Given a block that writes to buffer `B`, it factorizes a loop of extent `n`.

        For example, the pseudocode below accumulates `B[i] = sum(A[i, : , : ])`:

        .. code-block:: python

            for i in range(128):                    # loop i is a data parallel loop
                for j in range(128):                # loop j is a reduction loop
                    for k in range(128):            # loop k is a reduction loop
                        B[i] = B[i] + A[i, j, k]

        Suppose RFactor is applied on the innermost loop `k` and `factor_axis = 1`.
        RFactor then creates an intermediate buffer and two blocks.

        1. The intermediate buffer, or "rf-buffer" is a buffer of rank `ndim(B) + 1` and
        size `size(B) * n`, whose shape expands from `shape(B)` by adding an axis of `n`
        at the position specified by `factor_axis`. For example,

            * shape(B) = [1, 2, 3], factor_axis = 0  => shape(B_rf) = [n, 1, 2, 3]
            * shape(B) = [1, 2, 3], factor_axis = 1  => shape(B_rf) = [1, n, 2, 3]
            * shape(B) = [1, 2, 3], factor_axis = 2  => shape(B_rf) = [1, 2, n, 3]
            * shape(B) = [1, 2, 3], factor_axis = 3  => shape(B_rf) = [1, 2, 3, n]

        2. The rfactor block, or "rf-block", is a block that writes to the `rf-buffer` without
        accumulating over the loop `k`, i.e. the loop `k` is converted from a reduction loop
        to a data parallel loop. In our example, the rf-block is:

        .. code-block:: python

            B_rf = np.zeros((128, 128))     # the rf-buffer
            for k in range(128):            # loop k is converted to a data parallel loop
                for i in range(128):        # loop i is a data parallel loop (unchanged)
                    for j in range(128):    # loop j is a reduction loop (unchanged)
                        B_rf[i, k] = B_rf[i, k] + A[i, j, k]


        3. The write-back block, or `wb-block`, is a block that accumulates the rf-buffer into
        the result buffer. All the reduction loops are removed except the loop `k` for accumulation.
        In our example, the wb-block is:

        .. code-block:: python

            for i in range(128):            # loop i is a data parallel loop (unchanged)
                                            # loop j is removed because it is a reduction loop
                for k in range(128):        # loop k is a reduction loop (unchanged)
                    B[i] = B[i] + B_rf[i, k]


        Parameters
        ----------
        loop : LoopRV
            The loop outside block for which we want to do rfactor
        factor_axis : int
            The position where the new dimension is placed in the new introduced rfactor buffer

        Returns
        -------
        rf_block : BlockRV
            The block which computes partial results over each slices (i.e., the first block
            as described in the above illustration)

        Examples
        --------

        Before rfactor, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_rfactor(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, (128, 128, 128))
                B = T.match_buffer(b, (128,))
                for ii, i, j in T.grid(128, 128, 128):
                with T.block("B"):
                    vii, vi, vj = T.axis.remap("SRR", [ii, i, j])
                    with T.init():
                        B[vii] = 0.0
                    B[vii] = B[vii] + A[vii, vi, vj]

        Create the schedule and do rfactor:

        .. code-block:: python

            sch = tir.Schedule(before_rfactor)
            _, _, k = sch.get_loops(sch.get_block("B"))
            sch.rfactor(k, 0)
            print(sch.mod["main"].script())

        After applying rfactor, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_rfactor(a: T.handle, b: T.handle) -> None:
                A = T.match_buffer(a, [128, 128, 128])
                B = T.match_buffer(b, [128])
                B_rf = T.alloc_buffer([128, 128])
                for i2, ii, i in T.grid(128, 128, 128):
                    with T.block("B_rf"):
                        vi2, vii, vi = T.axis.remap("SSR", [i2, ii, i])
                        with T.init():
                            B_rf[vi2, vii] = 0.0
                        B_rf[vi2, vii] = (B_rf[vi2, vii] + A[vii, vi, vi2])
                for ii, i2 in T.grid(128, 128):
                    with T.block("B"):
                        vii, vi2 = T.axis.remap("SR", [ii, i2])
                        with T.init():
                            B[vii] = 0.0
                        B[vii] = B[vii] + B_rf[vi2, vii]


        Note
        ----

        Rfactor requires:
        1) `loop` has only one child block, and it is a reduction block;
        2) `loop` is a reduction loop, i.e. the loop variable is bound to only reduction variables
        in the block binding;
        3) `loop` is not parallelized, vectorized, unrolled or bound to any thread axis;
        4) The block scope that `loop` is in is a staged-pipeline;
        5) The outermost loop outside the reduction block should has the reduction block as its
        first child block;
        6) The outermost reduction loop should have only one child block;
        7) An unary extent loop that is not bound to any reduction or data parallel variables in
        the block binding should not appear under some reduction loop;
        8) The reduction block should write to only one buffer, and its init and body are both
        simple `BufferStore`s, and the pattern is registered as an associative reducer.
        The pre-defined patterns include: plus, multiplication, min and max;
        9) Each of the loops on top of the block cannot be bound to a data parallel and a
        reduction block binding at the same time;
        10) `factor_axis` should be in range `[-ndim(B) - 1, ndim(B)]`,
        where `B` is the buffer that the reduction block writes to.
        Negative indexing is normalized according to numpy convention.
        """
        return _ffi_api.ScheduleRFactor(self, loop, factor_axis)  # type: ignore # pylint: disable=no-member

    ######## Schedule: Block annotation ########

    @type_checked
    def storage_align(  # pylint: disable=too-many-arguments
        self,
        block: BlockRV,
        buffer_index: int,
        axis: int,
        factor: int,
        offset: int,
    ) -> None:
        """Set alignment requirement for specific dimension such that
        stride[axis] == k * factor + offset for some k. This is useful to set memory layout for more
        friendly memory access pattern. For example, we can set alignment to be factor=2, offset=1
        to avoid bank conflict for thread access on higher dimension in GPU shared memory.

        Parameters
        ----------
        block : BlockRV
            The producer block of the buffer.
        buffer_index : int
            The index of the buffer in block's write region.
        axis : int
            The dimension to be specified for alignment.
        factor : int
            The factor multiple of alignment.
        offset : int
            The required offset factor.

        Examples
        --------

        Before storage_align, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_storage_align(a: T.handle, c: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.alloc_buffer((128, 128))
                C = T.match_buffer(c, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0
                for i, j in T.grid(128, 128):
                    with T.block("C"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        C[vi, vj] = B[vi, vj] + 1.0

        Create the schedule and do storage_align:

        .. code-block:: python

            sch = tir.Schedule(before_storage_align)
            sch.storage_align(sch.get_block("B"), buffer_index=0, axis=0, factor=128, offset=1)
            print(sch.mod["main"].script())

        After applying storage_align, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_storage_align(a: T.handle, c: T.handle) -> None:
                A = T.match_buffer(a, (128, 128))
                B = T.alloc_buffer((128, 128))
                C = T.match_buffer(c, (128, 128))
                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        T.block_attr({"buffer_dim_align": [[[0, 128, 1]]]})
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0
                for i, j in T.grid(128, 128):
                    with T.block("C"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        C[vi, vj] = B[vi, vj] + 1.0

        After lowering passes, buffer B will have strides as [129, 1].

        Note
        ----
        Storage_align requires the buffer to be an intermediate buffer defined via `alloc_buffer`.
        """
        _ffi_api.ScheduleStorageAlign(  # type: ignore # pylint: disable=no-member
            self, block, buffer_index, axis, factor, offset
        )

    @type_checked
    def set_scope(self, block: BlockRV, buffer_index: int, storage_scope: str) -> None:
        """Set the storage scope of a buffer, where the buffer is
        specified by the a block and a write-index

        Parameters
        ----------
        block : BlockRV
            The producer block of the buffer
        buffer_index : int
            The index of the buffer in block's write region
        storage_scope : str
            The storage scope to be set

        Examples
        --------

        Before set_scope, in TensorIR, the IR is:

        .. code-block:: python

            @T.prim_func
            def before_set_scope(
                A: T.Buffer[(128, 128), "float32"], C: T.Buffer[(128, 128), "float32"]
            ) -> None:
                B = T.alloc_buffer((128, 128), dtype="float32")

                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B[vi, vj] = A[vi, vj] * 2.0
                for i, j in T.grid(128, 128):
                    with T.block("C"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        C[vi, vj] = B[vi, vj] + 1.0

        Create the schedule and do set_scope:

        .. code-block:: python

            sch = tir.Schedule(before_set_scope)
            sch.set_scope(sch.get_block("B"), buffer_index=0, storage_scope="shared")
            print(sch.mod["main"].script())

        After applying set_scope, the IR becomes:

        .. code-block:: python

            @T.prim_func
            def after_set_scope(
                A: T.Buffer[(128, 128), "float32"], C: T.Buffer[(128, 128), "float32"]
            ) -> None:
                B_shared = T.alloc_buffer([128, 128], dtype="float32", scope="shared")

                for i, j in T.grid(128, 128):
                    with T.block("B"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        B_shared[vi, vj] = A[vi, vj] * T.float32(2)
                for i, j in T.grid(128, 128):
                    with T.block("C"):
                        vi, vj = T.axis.remap("SS", [i, j])
                        C[vi, vj] = B_shared[vi, vj] + T.float32(1)

        Note
        ----
        Set_scope requires the buffer to be an intermediate buffer defined via `alloc_buffer`.
        """
        _ffi_api.ScheduleSetScope(  # type: ignore # pylint: disable=no-member
            self, block, buffer_index, storage_scope
        )

    ########## Schedule: Blockize & Tensorize ##########

    ########## Schedule: Annotation ##########

    ########## Schedule: Misc ##########

    @type_checked
    def enter_postproc(self) -> None:
        """A no-op that marks the start of postprocessing phase of scheduling"""
        _ffi_api.ScheduleEnterPostproc(self)  # type: ignore # pylint: disable=no-member
