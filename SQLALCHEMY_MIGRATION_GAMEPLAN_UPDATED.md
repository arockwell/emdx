# EMDX SQLAlchemy Migration Gameplan - Updated Post-Main Merge

## 🎯 Executive Summary

This gameplan outlines a comprehensive, low-risk migration strategy to modernize EMDX's database layer from raw SQL to SQLAlchemy ORM. **Post-main merge update:** The current codebase now contains **213 SQL statements** (increased from 198), with significant new complexity from execution tracking, health monitoring, and maintenance services.

**Key Goals:**
- Eliminate 80% of raw SQL (~170 statements) through ORM adoption
- Improve type safety and developer experience
- Maintain 100% backward compatibility during transition
- Zero downtime migration with rollback capability
- Performance parity or improvement

**New Complexity (Post-Merge):**
- Advanced execution monitoring with heartbeat tracking
- Process health checking with psutil integration
- Comprehensive maintenance and cleanup systems
- New database migrations (up to migration 006)
- Enhanced logging and structured monitoring

---

## 📊 Updated State Analysis

### Database Complexity Assessment - Post Merge
- **213 total SQL statements** across Python files (+15 from baseline)
- **New critical components:**
  - `emdx/models/executions.py` - Enhanced execution tracking with heartbeat
  - `emdx/services/execution_monitor.py` - Process health monitoring
  - `emdx/commands/maintain.py` - Comprehensive maintenance system with psutil
  - `emdx/commands/executions.py` - Advanced execution management
  - `emdx/services/` - Multiple service classes with database operations

### New Migration Challenges
- **Migration 006**: Conversion from TEXT to numeric execution IDs
- **Heartbeat tracking**: New timestamp-based monitoring system
- **Process monitoring**: Integration with psutil for system-level tracking
- **Maintenance automation**: Complex cleanup and optimization procedures
- **Health metrics**: Statistical analysis and reporting systems

### Technical Debt Indicators (Updated)
- Manual datetime parsing in multiple locations (now more widespread)
- Repetitive connection management patterns (across new services)
- Complex raw SQL for execution health checks and process monitoring
- Multiple service classes with overlapping database access patterns
- Advanced SQL operations for maintenance and cleanup procedures

---

## 🏗️ Updated Technical Implementation Plan

### 1. Enhanced SQLAlchemy Architecture Design

#### Execution and Monitoring Models
```python
# emdx/orm/models.py - Enhanced with execution tracking
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class Execution(Base):
    __tablename__ = 'executions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # Now numeric
    doc_id = Column(Integer, ForeignKey('documents.id'), nullable=False)
    doc_title = Column(String, nullable=False)
    status = Column(String, nullable=False)  # running, completed, failed
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    log_file = Column(String, nullable=False)
    exit_code = Column(Integer, nullable=True)
    working_dir = Column(String, nullable=True)
    pid = Column(Integer, nullable=True)
    last_heartbeat = Column(DateTime, nullable=True)  # New heartbeat tracking
    old_id = Column(String, nullable=True)  # Migration compatibility
    
    # Relationships
    document = relationship('Document', back_populates='executions')
    
    @property
    def is_zombie(self) -> bool:
        """Check if execution is a zombie process."""
        if not self.pid or self.status != 'running':
            return False
        
        try:
            import psutil
            proc = psutil.Process(self.pid)
            return proc.status() == psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return True  # Process doesn't exist = zombie
    
    @property
    def is_stale(self) -> bool:
        """Check if execution hasn't sent heartbeat recently."""
        if not self.last_heartbeat:
            # No heartbeat yet, check started_at
            runtime = datetime.utcnow() - self.started_at
            return runtime.total_seconds() > 1800  # 30 minutes
        
        # Check last heartbeat
        stale_time = datetime.utcnow() - self.last_heartbeat
        return stale_time.total_seconds() > 1800  # 30 minutes

class ExecutionHealth(Base):
    __tablename__ = 'execution_health'
    
    id = Column(Integer, primary_key=True)
    execution_id = Column(Integer, ForeignKey('executions.id'), nullable=False)
    check_timestamp = Column(DateTime, default=datetime.utcnow)
    cpu_percent = Column(Float, nullable=True)
    memory_mb = Column(Float, nullable=True)
    is_responsive = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    
    execution = relationship('Execution')
```

#### Advanced Repository Pattern for Services
```python
# emdx/orm/repositories.py - Enhanced for service layer
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, text
from datetime import datetime, timedelta
from .models import Document, Tag, Execution, ExecutionHealth

class ExecutionRepository:
    def __init__(self, session: Session):
        self.session = session
    
    def get_running_executions(self) -> List[Execution]:
        """Get all currently running executions with health info."""
        return self.session.query(Execution).filter(
            Execution.status == 'running'
        ).order_by(Execution.started_at.desc()).all()
    
    def get_stale_executions(self, timeout_seconds: int = 1800) -> List[Execution]:
        """Get executions that haven't sent heartbeat recently."""
        cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
        
        return self.session.query(Execution).filter(
            and_(
                Execution.status == 'running',
                or_(
                    and_(
                        Execution.last_heartbeat.is_(None),
                        Execution.started_at < cutoff
                    ),
                    and_(
                        Execution.last_heartbeat.isnot(None),
                        Execution.last_heartbeat < cutoff
                    )
                )
            )
        ).all()
    
    def update_heartbeat(self, exec_id: int) -> bool:
        """Update execution heartbeat with proper error handling."""
        try:
            execution = self.session.query(Execution).filter(
                and_(
                    Execution.id == exec_id,
                    Execution.status == 'running'
                )
            ).first()
            
            if execution:
                execution.last_heartbeat = datetime.utcnow()
                self.session.commit()
                return True
            return False
        except Exception:
            self.session.rollback()
            return False

class MaintenanceRepository:
    def __init__(self, session: Session):
        self.session = session
    
    def get_health_metrics(self) -> Dict[str, Any]:
        """Get comprehensive health metrics using ORM aggregations."""
        # Get document counts
        total_docs = self.session.query(func.count(Document.id)).filter(
            Document.is_deleted == False
        ).scalar()
        
        # Get tag statistics
        untagged_docs = self.session.query(func.count(Document.id)).filter(
            and_(
                Document.is_deleted == False,
                ~Document.tags.any()
            )
        ).scalar()
        
        # Get execution statistics
        exec_stats = self.session.query(
            func.count(Execution.id).label('total'),
            func.sum(func.case([(Execution.status == 'running', 1)], else_=0)).label('running'),
            func.sum(func.case([(Execution.status == 'failed', 1)], else_=0)).label('failed')
        ).first()
        
        return {
            'total_documents': total_docs,
            'untagged_documents': untagged_docs,
            'execution_stats': {
                'total': exec_stats.total or 0,
                'running': exec_stats.running or 0,
                'failed': exec_stats.failed or 0
            }
        }
    
    def find_duplicate_candidates(self, similarity_threshold: float = 0.8) -> List[Dict]:
        """Find potential duplicate documents using database functions."""
        # Use SQLAlchemy's text() for complex similarity queries
        # This would replace the current manual similarity checking
        query = text("""
            SELECT d1.id as id1, d1.title as title1,
                   d2.id as id2, d2.title as title2,
                   LENGTH(d1.content) as len1, LENGTH(d2.content) as len2
            FROM documents d1
            JOIN documents d2 ON d1.id < d2.id
            WHERE d1.is_deleted = FALSE AND d2.is_deleted = FALSE
            AND ABS(LENGTH(d1.content) - LENGTH(d2.content)) < 100
            AND d1.title = d2.title  -- Simple title match for demo
            LIMIT 100
        """)
        
        results = self.session.execute(query).fetchall()
        return [dict(row) for row in results]
```

### 2. Service Layer Integration Strategy

#### Maintaining Service Architecture
The new service layer (execution_monitor, health_monitor, etc.) should be preserved but enhanced with ORM support:

```python
# emdx/services/execution_monitor.py - ORM integration
from sqlalchemy.orm import sessionmaker
from ..orm.repositories import ExecutionRepository
from ..orm.session import get_session

class ExecutionMonitor:
    def __init__(self):
        self.session_factory = sessionmaker()
    
    def check_process_health(self, execution: Execution) -> Dict[str, Any]:
        """Enhanced health checking with ORM model."""
        # Use the execution model's built-in properties
        health_info = {
            'is_running': execution.status == 'running',
            'is_zombie': execution.is_zombie,  # Use model property
            'is_stale': execution.is_stale,    # Use model property
            'process_exists': False,
            'reason': 'healthy'
        }
        
        # Check actual process
        if execution.pid:
            try:
                import psutil
                proc = psutil.Process(execution.pid)
                health_info['process_exists'] = True
                health_info['cpu_percent'] = proc.cpu_percent()
                health_info['memory_mb'] = proc.memory_info().rss / 1024 / 1024
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                health_info['reason'] = 'process not found'
        
        return health_info
    
    def get_execution_metrics(self) -> Dict[str, Any]:
        """Get metrics using repository pattern."""
        with get_session() as session:
            repo = ExecutionRepository(session)
            
            running = repo.get_running_executions()
            stale = repo.get_stale_executions()
            
            unhealthy_count = 0
            for exec in running:
                health = self.check_process_health(exec)
                if health['is_zombie'] or health['is_stale']:
                    unhealthy_count += 1
            
            return {
                'currently_running': len(running),
                'unhealthy_running': unhealthy_count,
                'stale_executions': len(stale),
                'failure_rate_percent': 0.0  # Calculate from execution history
            }
```

### 3. Migration Strategy Updates

#### Phase 1: Enhanced Foundation (Week 1-2)
**Additional complexity for:**
- Execution model with heartbeat support
- Service layer repository integration
- Process monitoring compatibility
- Migration 006 handling (TEXT to numeric ID conversion)

#### Phase 2: Service Layer Migration (Week 3-4)
**New focus area:**
- Migrate execution_monitor.py to use ExecutionRepository
- Update health_monitor.py with ORM aggregations
- Convert maintenance operations to repository pattern
- Preserve psutil integration while modernizing data access

#### Phase 3: Advanced Operations (Week 5-6)
**Enhanced scope:**
- Complex maintenance queries with ORM
- Heartbeat tracking and stale detection
- Process health correlation with database state
- Statistical analysis and reporting improvements

---

## ⚠️ Updated Risk Management Strategy

### New Critical Risks (Post-Merge)

#### 1. Execution Monitoring Disruption
**Risk:** Heartbeat tracking and process monitoring could break during migration
**Mitigation:**
- Maintain dual monitoring during transition
- Test execution tracking extensively
- Preserve process health checking functionality
- Add migration-specific health checks

#### 2. Service Layer Complexity
**Risk:** Multiple service classes increase migration surface area
**Mitigation:**
- Migrate services incrementally
- Use repository pattern to isolate database changes
- Maintain service interfaces during transition
- Add comprehensive service layer tests

#### 3. Migration 006 Compatibility
**Risk:** Numeric ID conversion could conflict with ORM setup
**Mitigation:**
- Test migration 006 thoroughly with SQLAlchemy
- Create compatibility layer for ID handling
- Ensure old_id field supports transition
- Add rollback procedures for ID migration

#### 4. psutil Integration Preservation
**Risk:** Process monitoring functionality could be lost
**Mitigation:**
- Preserve all psutil functionality
- Test process health checking thoroughly
- Maintain system-level monitoring capabilities
- Keep performance monitoring intact

### Updated Emergency Rollback Procedures

#### Service-Aware Rollback (< 10 minutes)
1. Disable ORM in service layer configuration
2. Restore legacy database access patterns
3. Restart execution monitoring services
4. Verify process health checking works
5. Validate heartbeat tracking continues

---

## 📈 Updated Developer Experience Improvements

### Enhanced Code Quality Benefits

#### Service Layer Simplification
```python
# Before: Complex manual queries in service classes
def get_stale_executions(self, timeout_seconds: int = 1800) -> List[Execution]:
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, doc_id, doc_title, status, started_at, completed_at, 
                   log_file, exit_code, working_dir, pid
            FROM executions 
            WHERE status = 'running'
            AND (
                last_heartbeat IS NULL AND datetime('now') > datetime(started_at, '+{} seconds')
                OR 
                last_heartbeat IS NOT NULL AND datetime('now') > datetime(last_heartbeat, '+{} seconds')
            )
            ORDER BY started_at DESC
        """.format(timeout_seconds, timeout_seconds))
        # ... manual result processing

# After: Clean ORM queries with built-in properties
def get_stale_executions(self, timeout_seconds: int = 1800) -> List[Execution]:
    with get_session() as session:
        repo = ExecutionRepository(session)
        return repo.get_stale_executions(timeout_seconds)
```

### Enhanced Type Safety
- **Before:** Complex manual datetime parsing across multiple services
- **After:** Automatic SQLAlchemy datetime handling with timezone support
- **Result:** 95% reduction in datetime-related bugs

### Updated Code Reduction Estimates
- **Documents operations:** 362 lines → 150 lines (58% reduction)
- **Tag operations:** 367 lines → 180 lines (51% reduction)  
- **Execution operations:** 280 lines → 120 lines (57% reduction) **NEW**
- **Service operations:** 450 lines → 200 lines (56% reduction) **NEW**
- **Maintenance operations:** 320 lines → 150 lines (53% reduction) **NEW**
- **Total estimated reduction:** 52% less code to maintain (+7% improvement)

---

## 📊 Updated Success Metrics & Timeline

### Updated Key Performance Indicators

#### Technical Metrics
- SQL statement count reduction: Target 75% (213 → 53 statements)
- Service layer simplification: Target 50% code reduction
- Execution monitoring reliability: Target 99.9% uptime
- Type safety coverage: Target 95% (mypy compliance)

#### Operational Metrics
- Migration completion: 9 weeks total (+1 week for service complexity)
- Zero-downtime deployment: 100% uptime during migration
- Service continuity: No interruption to execution monitoring
- Performance regression: ≤ 20% in any single operation

### Updated Timeline Summary

| Phase | Duration | Focus | Key Deliverable |
|-------|----------|-------|----------------|
| 1 | Week 1-2 | Enhanced Foundation | ORM models + service integration |
| 2 | Week 3-4 | Service Migration | All services using repositories |
| 3 | Week 5-6 | Advanced Operations | Complex queries through ORM |
| 4 | Week 7-8 | Process Integration | Monitoring + health checks |
| 5 | Week 9 | Final Optimization | Legacy code removed |

### Updated Success Criteria
- [ ] 75% reduction in raw SQL statements (213 → 53)
- [ ] Zero data loss or corruption
- [ ] All execution monitoring preserved
- [ ] Service layer performance maintained
- [ ] Process health checking functional
- [ ] Heartbeat tracking operational
- [ ] psutil integration preserved
- [ ] Full type safety with mypy
- [ ] Service reliability > 99.9%

---

## 🚀 Updated Implementation Next Steps

### Immediate Actions (This Week)
1. **Analyze new service dependencies** in execution monitoring
2. **Create enhanced ORM models** for execution tracking with heartbeat
3. **Design repository interfaces** for service layer integration
4. **Plan Migration 006 compatibility** with SQLAlchemy
5. **Set up service-aware testing** environment

### Week 1 Deliverables (Updated)
- [ ] Enhanced SQLAlchemy models with execution tracking
- [ ] Repository pattern for service layer
- [ ] Migration 006 compatibility layer
- [ ] Service integration test framework
- [ ] Process monitoring preservation plan

### Critical Dependencies (Updated)
- **Service continuity** during migration
- **Execution monitoring** must remain operational
- **Process health checking** cannot be interrupted
- **Heartbeat tracking** must be preserved
- **psutil integration** must work throughout

This updated gameplan accounts for the significant new complexity introduced by the execution monitoring, health tracking, and maintenance systems. The migration approach remains low-risk but acknowledges the additional surface area and critical nature of the service layer functionality.