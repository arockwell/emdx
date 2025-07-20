# File Browser Performance & Architecture Fix Gameplan

## 🎯 Executive Summary

The file browser currently suffers from significant performance and architecture issues compared to the document and log browsers. This gameplan addresses:

- **Performance bottlenecks**: No caching, synchronous I/O, inefficient file system operations
- **Architecture problems**: Scattered responsibilities, complex widget recreation, memory leaks
- **UX inconsistencies**: Poor responsiveness, inconsistent behaviors vs other browsers
- **Memory management**: Excessive widget creation/destruction, content loading issues

## 🔍 Current Issues Analysis

### Performance Issues
1. **No caching layer**: Every directory change re-scans the entire file system
2. **Blocking I/O**: File content reading blocks the UI thread
3. **Memory inefficiency**: Constant widget recreation instead of reuse
4. **Inefficient EMDX checks**: Database queries for every file on every refresh
5. **Large file handling**: No size limits or streaming for preview content

### Architecture Problems
1. **Mixed responsibilities**: FileBrowser handles navigation, preview, editing, and modals
2. **Widget lifecycle issues**: Complex mount/unmount cycles with potential memory leaks
3. **Tight coupling**: Direct database calls scattered throughout UI code
4. **Mode switching complexity**: Edit/selection modes require full widget recreation
5. **Event handling inconsistencies**: Multiple key handling paths causing conflicts

### UX Inconsistencies
1. **Slow responsiveness**: Noticeable lag when navigating large directories
2. **Inconsistent keybindings**: Different behavior patterns vs document browser
3. **Poor error handling**: Permission errors don't provide clear user feedback
4. **Missing features**: No search, limited sorting options

## 🚀 Solution Architecture

### Phase 1: Core Performance Wins (Week 1)

#### 1.1 Implement Caching Layer
**Priority: Critical**

Create `emdx/ui/file_cache.py`:
```python
@dataclass
class DirectoryCache:
    path: Path
    files: List[FileInfo]
    last_modified: float
    access_time: float

class FileSystemCache:
    def __init__(self, max_size: int = 100):
        self._cache: Dict[Path, DirectoryCache] = {}
        self._max_size = max_size
        self._access_order: List[Path] = []
    
    def get_directory(self, path: Path) -> Optional[DirectoryCache]:
        # Check if cache is valid
        # Return cached data if fresh
        
    def invalidate_path(self, path: Path):
        # Remove path and children from cache
```

**Benefits:**
- 90% reduction in file system calls for previously visited directories
- Sub-100ms navigation between cached directories
- Automatic cache invalidation based on directory modification time

#### 1.2 Async File Operations
**Priority: Critical**

Replace synchronous I/O with async operations:
```python
class AsyncFileLoader:
    async def load_directory_contents(self, path: Path) -> List[FileInfo]:
        # Non-blocking directory listing
        
    async def load_file_preview(self, path: Path, max_size: int = 1024*1024) -> str:
        # Streaming file content with size limits
        
    async def check_emdx_status(self, files: List[Path]) -> Dict[Path, bool]:
        # Batch EMDX existence checks
```

**Benefits:**
- UI remains responsive during file operations
- Large directories don't freeze the interface
- Proper handling of slow network file systems

#### 1.3 Smart Content Handling
**Priority: High**

Implement intelligent content loading:
- **Size limits**: Preview only first 50KB of files
- **Type detection**: Skip binary files for text preview
- **Streaming**: Load content progressively for large files
- **Debouncing**: Avoid rapid preview updates during navigation

### Phase 2: Architecture Cleanup (Week 2)

#### 2.1 Separate Concerns
**Priority: High**

Extract specialized components:
```
file_browser.py (coordinator only)
├── file_list_view.py (file listing + navigation)
├── file_preview_pane.py (content preview)
├── file_operations.py (save/execute/edit actions)
└── file_cache.py (caching layer)
```

#### 2.2 Implement State Management
**Priority: High**

Create `FileSystemState` dataclass:
```python
@dataclass
class FileSystemState:
    current_path: Path
    selected_index: int
    show_hidden: bool
    sort_by: str
    filter_text: str
    cache: FileSystemCache
```

**Benefits:**
- Predictable state updates
- Easy undo/redo functionality
- Better testing through isolated state

#### 2.3 Widget Reuse Strategy
**Priority: Medium**

Replace widget recreation with state updates:
- Keep widgets alive, update their content
- Use reactive properties for mode switching
- Implement proper cleanup for memory management

### Phase 3: Memory Management (Week 2-3)

#### 3.1 Fix Widget Lifecycle
**Priority: High**

- **Proper cleanup**: Ensure all event handlers are removed
- **Memory pools**: Reuse TextArea widgets instead of recreation
- **Weak references**: Avoid circular references in event handlers
- **Lazy loading**: Create expensive widgets only when needed

#### 3.2 Content Streaming
**Priority: Medium**

For large files and directories:
- **Virtual scrolling**: Only render visible file list items
- **Progressive loading**: Load file metadata in chunks
- **Background prefetch**: Anticipate likely next directories

### Phase 4: UX Consistency (Week 3)

#### 4.1 Standardize Navigation
**Priority: Medium**

Align with document browser patterns:
- **Consistent keybindings**: Same navigation keys across browsers
- **Search integration**: Implement `/` search like document browser
- **Status feedback**: Rich status messages with progress indication

#### 4.2 Error Handling
**Priority: Medium**

Implement robust error handling:
- **Permission errors**: Clear user feedback with suggested actions
- **Network failures**: Graceful degradation for network file systems
- **Recovery mechanisms**: Automatic retry for transient failures

#### 4.3 Advanced Features
**Priority: Low**

Add missing capabilities:
- **File search**: Find files by name/content
- **Sorting options**: Multiple sort criteria
- **Bookmarks**: Quick access to frequently used directories
- **Recent files**: Track recently accessed files

### Phase 5: Integration & Testing (Week 4)

#### 5.1 Performance Testing
**Priority: High**

Create benchmarks for:
- **Directory loading**: Target <100ms for 1000+ files
- **Memory usage**: Track memory growth over time
- **Cache efficiency**: Measure hit rates and performance gains

#### 5.2 Browser Consistency
**Priority: Medium**

Ensure consistent behavior across document, log, and file browsers:
- **Shared components**: Extract common widgets
- **Unified styling**: Consistent visual design
- **Common keybindings**: Standardized navigation patterns

## 📊 Performance Targets

### Current vs Target Performance

| Operation | Current | Target | Improvement |
|-----------|---------|--------|-------------|
| Large directory load | 2-5s | <100ms | 20-50x |
| File preview | 500ms | <50ms | 10x |
| Directory switch | 1-2s | <50ms | 20-40x |
| Memory usage (4h session) | 500MB+ | <100MB | 5x |
| EMDX status check | 100ms/file | 5ms/batch | 20x |

### Memory Efficiency
- **Widget reuse**: 80% reduction in widget allocations
- **Cache management**: LRU eviction to maintain bounded memory
- **Content streaming**: Handle files up to 1GB without memory spikes

## 🛠 Implementation Approach

### Incremental Rollout Strategy

#### Week 1: Foundation
1. **Day 1-2**: Implement caching layer and basic async operations
2. **Day 3-4**: Add content size limits and streaming
3. **Day 5**: Performance testing and optimization

#### Week 2: Architecture
1. **Day 1-2**: Extract file list and preview components
2. **Day 3-4**: Implement state management
3. **Day 5**: Widget lifecycle improvements

#### Week 3: Optimization
1. **Day 1-2**: Memory management fixes
2. **Day 3-4**: UX consistency improvements
3. **Day 5**: Error handling and recovery

#### Week 4: Polish
1. **Day 1-2**: Advanced features (search, sorting)
2. **Day 3-4**: Integration testing
3. **Day 5**: Documentation and cleanup

### Risk Mitigation

#### Technical Risks
- **Regression risk**: Maintain backward compatibility during refactor
- **Performance risk**: Benchmark each change to ensure improvements
- **Memory risk**: Use profiling tools to detect memory leaks

#### Mitigation Strategies
- **Feature flags**: Enable new implementation gradually
- **A/B testing**: Compare old vs new performance side-by-side
- **Rollback plan**: Keep old implementation available as fallback

## 🧪 Testing Strategy

### Performance Tests
```python
def test_large_directory_performance():
    # Load directory with 5000+ files
    # Assert load time < 100ms
    
def test_memory_stability():
    # Navigate 100+ directories
    # Assert memory growth < 10MB
    
def test_cache_efficiency():
    # Navigate back/forth between directories
    # Assert 90%+ cache hit rate
```

### Integration Tests
- **Cross-browser consistency**: Ensure same behavior patterns
- **Error scenarios**: Test permission failures, network issues
- **Large file handling**: Test with files up to 1GB

### User Experience Tests
- **Responsiveness**: No operations should block UI >100ms
- **Feedback**: All operations provide clear status updates
- **Recovery**: Graceful handling of all error conditions

## 📈 Success Metrics

### Performance KPIs
1. **Load time**: 95th percentile directory load <100ms
2. **Memory efficiency**: <100MB sustained memory usage
3. **Cache hit rate**: >90% for recently visited directories
4. **UI responsiveness**: Zero blocking operations >100ms

### User Experience KPIs
1. **Navigation speed**: Instant response to key presses
2. **Error recovery**: Clear feedback for all error conditions
3. **Feature parity**: Match document browser capabilities
4. **Consistency**: Unified behavior across all browsers

### Code Quality KPIs
1. **Test coverage**: >90% coverage for core components
2. **Cyclomatic complexity**: <10 for all methods
3. **Code duplication**: <5% duplicate code
4. **Documentation**: 100% public API documented

## 🎉 Expected Outcomes

### Immediate Benefits (Post Phase 1)
- **20-50x faster** directory navigation
- **Responsive UI** during all file operations
- **Better memory usage** with bounded growth

### Medium-term Benefits (Post Phase 3)
- **Consistent UX** across all browsers
- **Robust error handling** with clear user feedback
- **Advanced features** like search and sorting

### Long-term Benefits (Post Phase 4)
- **Maintainable architecture** with clear separation of concerns
- **Extensible design** for future file browser features
- **Performance benchmark** for other EMDX components

## 🏗 Next Steps

1. **Review and approve** this gameplan with stakeholders
2. **Set up performance benchmarking** infrastructure
3. **Create feature flags** for gradual rollout
4. **Begin Phase 1 implementation** with caching layer
5. **Establish testing protocols** for each phase

This gameplan transforms the file browser from a performance bottleneck into a fast, responsive, and maintainable component that matches the quality level of EMDX's document and log browsers.