---
layout: post
author: Bob
categories:
  - ports & adapters
tags:
  - python
  - architecture
---

In the first and second parts of this series I introduced the
[Command-Handler]({% post_url 2017-09-07-introducing-command-handler %})
and
[Unit of Work and Repository patterns]({% post_url 2017-09-08-repository-and-unit-of-work-pattern-in-python %}).
I was intending to write about Message Buses, and some more stuff
about domain modelling, but I need to quickly skim over this first.

If you've just started reading the Message Buses piece, and you're here to learn
about Application-Controlled Identifiers, you'll find those at the end of post,
after a bunch of stuff about ORMs, CQRS, and some casual trolling of junior
programmers.

### What is CQS ?

The [Command Query Separation](https://martinfowler.com/bliki/CommandQuerySeparation.html)
principle was first described by Bertrand Meyer in the late Eighties. Per
[wikipedia](https://en.wikipedia.org/wiki/Command%E2%80%93query_separation),
the principle states:

every method should either be a command that performs an action, or a query that
returns data to the caller, but not both. In other words, "Asking a question
should not change the answer". More formally, methods should return a value only
if they are referentially transparent and hence possess no side effects.

Referential transparency is an important concept from functional programming.
Briefly, a function is referentially transparent if you could replace it with a
static value.

```python
class LightSwitch:

    def toggle_light(self):
        self.light_is_on = not self.light_is_on
        return self.light_is_on

    @property
    def is_on(self):
        return self.light_is_on
```

In this class, the is_on  method is referentially transparent - I can replace it
with the value True or False without any loss of functionality, but the method
toggle_light  is side-effectual: replacing its calls with a static value would
break the contracts of the system. To comply with the Command-Query separation
principle, we should not return a value from our toggle_light  method.

In some languages we would say that the is_on method is "pure". The advantage of
splitting our functions into those that have side effects and those that are
pure is that the code becomes easier to reason about. Haskell loves pure
functions, and uses this reasonability to do strange things, like re-ordering
your code for you at compilation time to make it more efficient. For those of us
who work in more prosaic languages, if commands and queries are clearly
distinguished, then I can read through a code base and understand all the ways
in which state can change. This is a huge win for debugging because there is
nothing worse than troubleshooting a system when you can't work out which
code-paths are changing your data.

How do we get data out of a Command-Handler architecture?
When we're working in a Command-Handler system we obviously use Commands and
Handlers to perform state changes, but what should we do when we want to get
data back out of our model? What is the equivalent port for queries?

The answer is "it depends". The lowest-cost option is just to re-use your
repositories in your UI entrypoints.

```python
@app.route("/issues")
def list_issues():
    with unit_of_work_manager.start() as unit_of_work:
        open_issues = unit_of_work.issues.find_by_status('open')
        return json.dumps(open_issues)
```

This is totally fine unless you have complex formatting, or multiple entrypoints
to your system. The problem with using your repositories directly in this way is
that it's a slippery slope. Sooner or later you're going to have a tight
deadline, and a simple requirement, and the temptation is to skip all the
command/handler nonsense and do it directly in the web api.

```python
@app.route('/issues/<issue_id>', methods=['DELETE'])
def delete_issue(issue_id):
     with unit_of_work_manager.start() as uow:
         issue = uow.issues[issue_id]
         issue.delete()
         uow.commit()
```

Super convenient, but then you need to add some error handling and some logging
and an email notification.

```python
@app.route('/issues/<issue_id>', methods=['DELETE'])
def delete_issue(issue_id):
    logging.info("Handling DELETE of issue "+str(issue_id))

    with unit_of_work_manager.start() as uow:
       issue = uow.issues[issue_id]

       if issue is None:
           logging.warn("Issue not found")
           flask.abort(404)
       if issue.status != 'deleted':
          issue.delete()
          uow.commit()
          try:
             smtp.send_notification(Issue.Deleted, issue_id)
          except:
             logging.error(
                "Failed to send email notification for deleted issue "
                 + str(issue_id), exn_info=True)
       else:
          logging.info("Issue already deleted. NOOP")
    return "Deleted!", 202
```


Aaaaand, we're back to where we started: business logic mixed with glue code,
and the whole mess slowly congealing in our web controllers. Of course, the
slippery slope argument isn't a good reason not to do something, so if your
queries are very simple, and you can avoid the temptation to do updates from
your controllers, then you might as well go ahead and read from repositories,
it's all good, you have my blessing. If you want to avoid this, because your
reads are complex, or because you're trying to stay pure, then instead we could
define our views explicitly.

```python
class OpenIssuesList:

    def __init__(self, sessionmaker):
        self.sessionmaker = sessionmaker

    def fetch(self):
        with self.sessionmaker() as session:
            result = session.execute(
                'SELECT reporter_name, timestamp, title
                 FROM issues WHERE state="open"')
            return [dict(r) for r in result.fetchall()]


@api.route('/issues/')
def list_issues():
    view_builder = OpenIssuesList(session_maker)
    return jsonify(view_builder.fetch())
```

This is my favourite part of teaching ports and adapters to junior programmers,
because the conversation inevitably goes like this:

> smooth-faced youngling: Wow, um... are you - are we just going to hardcode that
> sql in there? Just ... run it on the database?

> grizzled old architect: Yeah, I think so. Do The Simplest Thing That Could
> Possibly Work, right? YOLO, and so forth.

> sfy: Oh, okay. Um... but what about the unit of work and the domain model and
> the service layer and the hexagonal stuff? Didn't you say that "Data access
> ought to be performed against the aggregate root for the use case, so that we
> maintain tight control of transactional boundaries"?

> goa: Ehhhh... I don't feel like doing that right now, I think I'm getting
> hungry.

> sfy: Right, right ... but what if your database schema changes?

> goa: I guess I'll just come back and change that one line of SQL. My acceptance
> tests will fail if I forget, so I can't get the code through CI.

> sfy: But why don't we use the Issue model we wrote? It seems weird to just
> ignore it and return this dict... and you said "Avoid taking a dependency
> directly on frameworks. Work against an abstraction so that if your dependency
> changes, that doesn't force change to ripple through your domain". You know we
> can't unit test this, right?

> goa: Ha! What are you, some kind of architecture astronaut? Domain models! Who
> needs 'em.

### Why have a separate read-model?

In my experience, there are two ways that teams go wrong when using ORMs. The
most common mistake is not paying enough attention to the boundaries of their
use cases. This leads to the application making far too many calls to the
database because people write code like this:

```python
# Find all users who are assigned this task
# [[and]] notify them and their line manager
# then move the task to their in-queue
notification = task.as_notification()
for assignee in task.assignees:
    assignee.manager.notifications.add(notification)
    assignee.notifications.add(notification)
    assignee.queues.inbox.add(task)
```


ORMs make it very easy to "dot" through the object model this way, and pretend
that we have our data in memory, but this quickly leads to performance issues
when the ORM generates hundreds of select statements in response. Then they get
all angry about performance and write long blog posts about how ORM sucks and is
an anti-pattern and only n00bs like it. This is akin to blaming OO for your
domain logic ending up in the controller.

The second mistake that teams make is using an ORM when they don't need to. Why
do we use an ORM in the first place? I think that a good ORM gives us two
things:

 1. A unit of work pattern which can be used to control our consistency
    boundaries.
 2. A data mapper pattern that lets us map a complex object graph to relational
    tables, without writing tons of boring glue code.

Taken together, these patterns help us to write rich domain models by removing
all the database cruft so we can focus on our use-cases. This allows us to model
complex business processes in an internally consistent way. When I'm writing a
GET method, though, I don't care about any of that. My view doesn't need any
business logic, because it doesn't change any state. For 99.5% of use cases, it
doesn't even matter if my data are fetched inside a transaction. If I perform a
dirty read when listing the issues, one of three things might happen:

 1. I might see changes that aren't yet committed - maybe an Issue that has just
    been deleted will still show up in the list.
 2. I might not see changes that have been committed - an Issue could be missing
    from the list, or a title might be 10ms out of date.
 3. I might see duplicates of my data - an Issue could appear twice in the list.

In many systems all these occurrences are unlikely, and will be resolved by a
page refresh or following a link to view more data. To be clear, I'm not
recommending that you turn off transactions for your SELECT statements, just
noting that transactional consistency is usually only a real requirement when we
are changing state. When viewing state, we can almost always accept a weaker
consistency model.

### CQRS is CQS at a system-level

CQRS stands for Command-Query Responsibility Segregation, and it's an
architectural pattern that was popularised by Greg Young. A lot of people
misunderstand CQRS, and think you need to use separate databases and crazy
asynchronous processors to make it work. You can  do these things, and I want to
write more about that later, but CQRS just means that we separate the Write
Model - what we normally think of as the domain model - and the Read Model - a
lightweight, simple model for showing on the UI, or answering questions about
the domain state.

When I'm serving a write request (a command), my job is to protect the invariants
of the system, and model the business process as it appears in the minds of our
domain experts. I take the collective understanding of our business analysts,
and turn it into a state machine that makes useful work happen. When I'm serving
a read request (a query), my job is to get the data out of the database as fast
as possible and onto a screen so the user can view it. Anything that gets in the
way of my doing that is bloat.


This isn't a new idea, or particularly controversial. We've all tried writing
reports against an ORM, or complex hierarchical listing pages, and hit
performance barriers. When we get to that point, the only thing we can do -
short of rewriting the whole model, or abandoning our use of an ORM - is to
rewrite our queries in raw SQL. Once upon a time I'd feel bad for doing this, as
though I were cheating, but nowadays I just recognise that the requirements for
my queries are fundamentally different than the requirements for my commands.

For the write-side of the system, use an ORM, for the read side, use whatever is
a) fast, and b) convenient.

### Application Controlled Identifiers

At this point, a non-junior programmer will say

> Okay, Mr Smarty-pants Architect, if our commands can't return any values, and
> our domain models don't know anything about the database, then how do I get an
> ID back from my save method?
> Let's say I create an API for creating new issues, and when I have POSTed the
> new issue, I want to redirect the user to an endpoint where they can GET their
> new Issue. How can I get the id back?

The way I would recommend you handle this is simple - instead of letting your
database choose ids for you, just choose them yourself.

```python
@api.route('/issues', methods=['POST'])
def report_issue(self):
    # uuids make great domain-controlled identifiers, because
    # they can be shared amongst several systems and are easy
    # to generate.
    issue_id = uuid.uuid4()

    cmd = ReportIssueCommand(issue_id, **request.get_json())
    handler.handle(cmd)
    return "", 201, { 'Location': '/issues/' + str(issue_id) }
```

There's a few ways to do this, the most common is just to use a UUID, but you
can also implement something like
[hi-lo](https://pypi.python.org/pypi/sqlalchemy-hilo/0.1.2).
In the new
[code sample](https://github.com/bobthemighty/blog-code-samples/tree/master/ports-and-adapters/03),
I've implemented three flask endpoints, one to create a new issue, one to list
all issues, and one to view a single issue. I'm using UUIDs as my identifiers,
but I'm still using an integer primary key on the issues table, because using a
GUID in a clustered index leads to table fragmentation and
[sadness](http://sqlmag.com/database-performance-tuning/clustered-indexes-based-upon-guids)
.

Okay, quick spot-check - how are we shaping up against our original Ports and
Adapters diagram? How do the concepts map?


Pretty well! Our domain is pure and doesn't know anything about infrastructure
or IO. We have a command and a handler that orchestrate a use-case, and we can
drive our application from tests or Flask. Most importantly, the layers on the
outside depend on the layers toward the centre.

Next time I'll get back to talking about message buses.
