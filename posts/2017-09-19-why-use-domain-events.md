title: Why use domain events?
author: Bob

---

Nota bene: this instalment in the Ports and Adapters with Command Handlers
series is code-heavy, and isn't going to make much sense unless you've read the
previous parts:

 * [Introducing Command Handler]({% post_url 2017-09-07-introducing-command-handler %})
 * [Repositories and Units of Work]({% post_url 2017-09-08-repository-and-unit-of-work-pattern-in-python %})
 * [Commands and Queries, Handlers and Views]({% post_url 2017-09-13-commands-and-queries-handlers-and-views %})

Okay, so we have a basic skeleton for an application and we can add new issues
into the database, then fetch them from a Flask API. So far, though, we don't
have any domain logic at all. All we have is a whole bunch of complicated crap
where we could just have a tiny Django app. Let's work through some more
use-cases and start to flesh things out.

Back to our domain expert:

So when we've added a reported issue to the issue log, what happens next?

Well we need to triage the problem and decide how urgent it is. Then we might
assign it to a particular engineer, or we might leave it on the queue to be
picked up by anyone.

Wait, the queue? I thought you had an issue log, are they the same thing, or is
there a difference?

Oh, yes. The issue log is just a record of all the issues we have received, but
we work from the queue.

I see, and how do things get into the queue?

We triage the new items in the issue log to decide how urgent they are, and what
categories they should be in. When we know how to categorise them, and how
urgent they are, we treat the issues as a queue, and work through them in
priority order.

This is because users always set things to "Extremely urgent"?

Yeah, it's just easier for us to triage the issues ourselves.

And what does that actually mean, like, do you just read the ticket and say "oh,
this is 5 important, and it's in the broken mouse category"?

Mmmm... more or less, sometimes we need to ask more questions from the user so
we'll email them, or call them. Most things are first-come, first-served, but
occasionally someone needs a fix before they can go to a meeting or something.

So you email the user to get more information, or you call them up, and then you
use that information to assess the priority of the issue - sorry triage the
issue, and work out what category it should go in... what do the categories 
achieve? Why categorise?

Partly for reporting, so we can see what stuff is taking up the most time, or if
there are clusters of similar problems on a particular batch of laptops for
example. Mostly because different engineers have different skills, like if you
have a problem with the Active Directory domain, then you should send that to
Barry, or if it's an Exchange problem, then George can sort it out, and Mike has
the equipment log so he can give you a temporary laptop and so on, and so on.

Okay, and where do I find this "queue"?

Your customer grins and gestures at the wall where a large whiteboard is covered
in post-its and stickers of different colours.

Mapping our requirements to our domain
How can we map these requirements back to our system? Looking back over our
notes with the domain expert, there's a few obvious verbs that we should use to
model our use cases. We can triage  an issue, which means we prioritise and
categorise it; we can assign  a triaged issue to an engineer, or an engineer can
 pick up  an unassigned issue. There's also a whole piece about asking
questions, which we might do synchronously by making a phone call and filling
out some more details, or asynchronously by sending an email. The Queue, with
all of its stickers and sigils and swimlanes looks too complicated to handle
today, so we'll dig deeper into that separately.

Let's quickly flesh out the triage use cases. We'll start by updating the
existing unit test for reporting an issue:

class When_reporting_an_issue:

    def given_an_empty_unit_of_work(self):
        self.uow = FakeUnitOfWork()

    def because_we_report_a_new_issue(self):
        handler = ReportIssueHandler(self.uow)
        cmd = ReportIssueCommand(id, name, email, desc)
        handler.handle(cmd)
        
    @property
    def issue(self):
        return self.uow.issues[0]

    def it_should_be_awaiting_triage(self):
        expect(self.issue.state).to(equal(IssueState.AwaitingTriage))


We're introducing a new concept - Issues now have a state, and a newly reported
issue begins in the AwaitingTriage  state. We can quickly add a command and
handler that allows us to triage an issue.

class TriageIssueHandler:

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def handle(self, cmd):
        with self.uowm.start() as uow:
            issue = uow.issues.get(cmd.issue_id)
            issue.triage(cmd.priority, cmd.category)
            uow.commit()


Triaging an issue, for now, is a matter of selecting a category and priority.
We'll use a free string for category, and an enumeration for Priority. Once an
issue is triaged, it enters the AwaitingAssignment  state. At some point we'll
need to add some view builders to list issues that are waiting for triage or
assignment, but for now let's quickly add a handler so that an engineer can Pick 
 an issue from the queue.

class PickIssueHandler:

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def handle(self, cmd):
        with self.uowm.start() as uow:
            issue = uow.issues.get(cmd.issue_id)
            issue.assign_to(cmd.picked_by)
            uow.commit()


At this point, the handlers are becoming a little boring. As I said way back in 
the first part [https://io.made.com/blog/introducing-command-handler/], commands
handlers are supposed to be boring glue-code, and every command handler has the
same basic structure:

 1. Fetch current state.
 2. Mutate the state by calling a method on our domain model.
 3. Persist the new state.
 4. Notify other parts of the system that our state has changed.

So far, though, we've only seen steps 1, 2, and 3. Let's introduce a new
requirement.

When an issue is assigned to an engineer, can we send them an email to let them
know?

A brief discourse on SRP
Let's try and implement this new requirement. Here's a first attempt:

class AssignIssueHandler:

    def __init__(self, 
               uowm: UnitOfWorkManager,
               email_builder: EmailBuilder,
               email_sender: EmailSender):
        self.uowm = uowm
        self.email_builder = email_builder
        self.email_sender = email_sender

    def handle(self, cmd):
        # Assign Issue
        with self.uowm.start() as uow:
            issue = uow.issues.get(cmd.issue_id)
            issue.assign_to(
                cmd.assigned_to,
                assigned_by=cmd.assigned_by
            )
            uow.commit()

        # Send Email                
        email = self.email_builder.build(
                cmd.assigned_to, 
                cmd.assigned_by,
                issue.problem_description)
        self.email_sender.send(email)


Something here feels wrong, right? Our command-handler now has two very distinct
responsibilities. Back at the beginning of this series we said we would stick
with three principles:

 1. We will always define where our use-cases begin and end.
 2. We will depend on abstractions, and not on concrete implementations.
 3. We will treat glue code as distinct from business logic, and put it in an
    appropriate place.

The latter two are being maintained here, but the first principle feels a little
more strained. At the very least we're violating the Single Responsibility
Principle [https://en.wikipedia.org/wiki/Single_responsibility_principle]; my
rule of thumb for the SRP is "describe the behaviour of your class. If you use
the word 'and' or 'then' you may be breaking the SRP". What does this class do?
It assigns an issue to an engineer, AND THEN sends them an email. That's enough
to get my refactoring senses tingling, but there's another, less theoretical,
reason to split this method up, and it's to do with error handling.

If I click a button marked "Assign to engineer", and I can't assign the issue to
that engineer, then I expect an error. The system can't execute the command I've
given to it, so I should retry, or choose a different engineer.

If I click a button marked "Assign to engineer", and the system succeeds, but
then can't send a notification email, do I care? What action should I take in
response? Should I assign the issue again? Should I assign it to someone else?
What state will the system be in if I do?

Looking at the problem in this way, it's clear that "assigning the issue" is the
real boundary of our use case, and we should either do that successfully, or
fail completely. "Send the email" is a secondary side effect. If that part fails
I don't want to see an error - let the sysadmins clear it up later.

What if we split out the notification to another class?

class AssignIssueHandler:

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def handle(self, cmd):
        with self.uowm.start() as uow:
            issue = uow.issues.get(cmd.issue_id)
            issue.assign_to(
                cmd.assignee_address,
                assigned_by=cmd.assigner_address
            )
            uow.commit()

        
class SendAssignmentEmailHandler
    def __init__(self, 
               uowm: UnitOfWorkManager,
               email_builder: EmailBuilder,
               email_sender: EmailSender):
        self.uowm = uowm
        self.email_builder = email_builder
        self.email_sender = email_sender

    def handle(self, cmd):
        with self.uowm.start() as uow:
            issue = uow.issues.get(cmd.issue_id)

            email = self.email_builder.build(
                cmd.assignee_address, 
                cmd.assigner_address,
                issue.problem_description)
            self.email_sender.send(email)


We don't really need a unit of work here, because we're not making any
persistent changes to the Issue state, so what if we use a view builder instead?

 class SendAssignmentEmailHandler
    def __init__(self, 
               view: IssueViewBuilder,
               email_builder: EmailBuilder,
               email_sender: EmailSender):
        self.view = view
        self.email_builder = email_builder
        self.email_sender = email_sender

    def handle(self, cmd):
        issue = self.view.fetch(cmd.issue_id)

        email = self.email_builder.build(
            cmd.assignee_address, 
            cmd.assigner_address,
            issue['problem_description'])
        self.email_sender.send(email)


That seems better, but how should we invoke our new handler? Building a new
command and handler from inside our AssignIssueHandler also sounds like a
violation of SRP. Worse still, if we start calling handlers from handlers, we'll
end up with our use cases coupled together again - and that's definitely  a
violation of Principle #1.

What we need is a way to signal between handlers - a way of saying "I did my
job, can you go do yours?"

All Aboard the Message Bus
In this kind of system, we use Domain Events
[http://verraes.net/2014/11/domain-events/]  to fill that need. Events are
closely related to Commands, in that both commands and events are types of 
message
[http://www.enterpriseintegrationpatterns.com/patterns/messaging/Message.html] 
- named chunks of data sent between entities. Commands and events differ only in
their intent:

 1. Commands are named with the imperative tense (Do this thing), events are
    named in the past tense (Thing was done).
 2. Commands must be handled by exactly one handler, events can be handled by 0
    to N handlers.
 3. If an error occurs when processing a command, the entire request should
    fail. If an error occurs while processing an event, we should fail
    gracefully.

We will often use domain events to signal that a command has been processed and
to do any additional book-keeping. When should we use a domain event? Going back
to our principle #1, we should use events to trigger workflows that fall outside
of our immediate use-case boundary. In this instance, our use-case boundary is
"assign the issue", and there is a second requirement "notify the assignee" that
should happen as a secondary result. Notifications, to humans or other systems,
are one of the most common reasons to trigger events in this way, but they might
also be used to clear a cache, or regenerate a view model, or execute some logic
to make the system eventually consistent.

Armed with this knowledge, we know what to do - we need to raise a domain event
when we assign an issue to an engineer. We don't want to know about the
subscribers to our event, though, or we'll remain coupled; what we need is a
mediator, a piece of infrastructure that can route messages to the correct
places. What we need is a message bus. A message bus is a simple piece of
middleware that's responsible for getting messages to the right listeners. In
our application we have two kinds of message, commands and events. These two
types of message are in some sense symmetrical, so we'll use a single message
bus for both.



How do we start off writing a message bus? Well, it needs to look up subscribers
based on the name of an event. That sounds like a dict to me:

class MessageBus:

    def __init__(self):
        """Our message bus is just a mapping from message type
           to a list of handlers"""
        self.subscribers = defaultdict(list)

    def handle(self, msg):
        """The handle method invokes each handler in turn
           with our event"""
        msg_name = type(msg).__name__
        subscribers = self.subscribers[msg_name]
        for subscriber in subscribers:
            subscriber.handle(cmd)
            
    def subscribe_to(self, msg, handler):
        """Subscribe sets up a new mapping, we make sure not
           to allow more than one handler for a command"""
        subscribers = [msg.__name__]
        if msg.is_cmd and len(subscribers) > 0:
           raise CommandAlreadySubscribedException(msg.__name__) 
        subscribers.append(handler)
        
# Example usage
bus = MessageBus()
bus.subscribe_to(ReportIssueCommand, ReportIssueHandler(db.unit_of_work_manager))
bus.handle(cmd)


Here we have a bare-bones implementation of a message bus. It doesn't do
anything fancy, but it will do the job for now. In a production system, the
message bus is an excellent place to put cross-cutting concerns; for example, we
might want to validate our commands before passing them to handlers, or we may
want to perform some basic logging, or performance monitoring. I want to talk
more about that in the next part, when we'll tackle the controversial subject of
dependency injection and Inversion of Control containers.

For now, let's look at how to hook this up. Firstly, we want to use it from our
API handlers.

@api.route('/issues', methods=['POST'])
def create_issue(self):
    issue_id = uuid.uuid4()
    cmd = ReportIssueCommand(issue_id=issue_id, **request.get_json())
    bus.handle(cmd)
    return "", 201, {"Location": "/issues/" + str(issue_id) }


Not much has changed here - we're still building our command in the Flask
adapter, but now we're passing it into a bus instead of directly constructing a
handler for ourselves. What about when we need to raise an event? We've got
several options for doing this. Usually I raise events from my command handlers,
like this:

class AssignIssueHandler:

    def handle(self, cmd):
        with self.uowm.start() as uow:
            issue = uow.issues.get(cmd.id)
            issue.assign_to(cmd.assigned_to, cmd.assigned_by)
            uow.commit()
            
        # This is step 4: notify other parts of the system 
        self.bus.raise(IssueAssignedToEngineer(
            cmd.issue_id,
            cmd.assigned_to,
            cmd.assigned_by))


I usually think of this event-raising as a kind of glue - it's orchestration
code. Raising events from your handlers this way makes the flow of messages
explicit - you don't have to look anywhere else in the system to understand
which events will flow from a command. It's also very simple in terms of
plumbing. The counter argument is that this feels like we're violating SRP in
exactly the same way as before - we're sending a notification about our
workflow. Is this really any different to sending the email directly from the
handler? Another option is to send events directly from our model objects, and
treat them as part our domain model proper.

class Issue:

    def assign_to(self, assigned_to, assigned_by):
        self.assigned_to = assigned_to
        self.assigned_by = assigned_by
        
        # Add our new event to a list
        self.events.add(IssueAssignedToEngineer(self.id, self.assigned_to, self.assigned_by))


There's a couple of benefits of doing this: firstly, it keeps our command
handler simpler, but secondly it pushes the logic for deciding when to send an
event into the model. For example, maybe we don't always  need to raise the
event.

class Issue:

    def assign_to(self, assigned_to, assigned_by):
        self.assigned_to = assigned_to
        self.assigned_by = assigned_by
        
        # don't raise the event if I picked the issue myself
        if self.assigned_to != self.assigned_by:
            self.events.add(IssueAssignedToEngineer(self.id, self.assigned_to, self.assigned_by))


Now we'll only raise our event if the issue was assigned by another engineer.
Cases like this are more like business logic than glue code, so today I'm
choosing to put them in my domain model. Updating our unit tests is trivial,
because we're just exposing the events as a list on our model objects:

class When_assigning_an_issue:

    issue_id = uuid.uuid4()
    assigned_to = 'ashley@example.org'
    assigned_by = 'laura@example.org'

    def given_a_new_issue(self):
        self.issue = Issue(self.issue_id, 'reporter@example.org', 'how do I even?')

    def because_we_assign_the_issue(self):
        self.issue.assign(self.assigned_to, self.assigned_by)

    def we_should_raise_issue_assigned(self):
        expect(self.issue).to(have_raised(
            IssueAssignedToEngineer(self.issue_id,
                                    self.assigned_to,
                                    self.assigned_by)))


The have_raised  function is a custom matcher I wrote that checks the events 
attribute of our object to see if we raised the correct event. It's easy to test
for the presence of events, because they're namedtuples, and have value
equality.

All that remains is to get the events off our model objects and into our message
bus. What we need is a way to detect that we've finished one use-case and are
ready to flush our changes. Fortunately, we have a name for this already - it's
a unit of work. In this system I'm using SQLAlchemy's event hooks
[http://docs.sqlalchemy.org/en/latest/orm/session_events.html]  to work out
which objects have changed, and queue up their events. When the unit of work
exits, we raise the events.

class SqlAlchemyUnitOfWork(UnitOfWork):

    def __init__(self, sessionfactory, bus):
        self.sessionfactory = sessionfactory
        self.bus = bus
        # We want to listen to flush events so that we can get events
        # from our model objects
        event.listen(self.sessionfactory, "after_flush", self.gather_events)
    
    def __enter__(self):
        self.session = self.sessionfactory()
        # When we first start a unit of work, create a list of events
        self.flushed_events = []
        return self

    def commit(self):
        self.session.flush()
        self.session.commit()

    def rollback(self):
        self.session.rollback()
        # If we roll back our changes we should drop all the events
        self.events = []
    
    def gather_events(self, session, ctx):
        # When we flush changes, add all the events from our new and 
        # updated entities into the events list
        flushed_objects = ([e for e in session.new]
                        + [e for e in session.dirty])
        for e in flushed_objects:
            self.flushed_events += e.events
            
    def publish_events(self):
        # When the unit of work completes
        # raise any events that are in the list
        for e in self.flushed_events:
            self.bus.handle(e)
        
    def __exit__(self, type, value, traceback):
        self.session.close()
        self.publish_events()


Okay, we've covered a lot of ground here. We've discussed why you might want to
use domain events, how a message bus actually works in practice, and how we can
get events out of our domain and into our subscribers. The newest code sample
[https://github.com/bobthemighty/blog-code-samples/tree/master/ports-and-adapters/04] 
 demonstrates these ideas, please do check it out, run it, open pull requests,
open Github issues etc.

Some people get nervous about the design of the message bus, or the unit of
work, but this is just infrastructure - it can be ugly, so long as it works.
We're unlikely to ever change this code after the first few user-stories. It's
okay to have some crufty code here, so long as it's in our glue layers, safely
away from our domain model. Remember, we're doing all of this so that our domain
model can stay pure and be flexible when we need to refactor. Not all layers of
the system are equal, glue code is just glue.

Next time I want to talk about Dependency Injection, why it's great, and why
it's nothing to be afraid of.
