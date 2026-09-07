"""Seed call transcripts.

Ten conversations written so that every capability in Salix has something real
to measure. They are not filler: each is shaped to produce a specific,
checkable result, and the word balance is deliberate.

That last point matters more than it sounds. In a real discovery call the rep
asks a short question and the buyer answers at length -- top performers land
near 43% of the talking. A script where the rep carries the exposition and the
buyer replies in one line produces a top performer who measures worse than the
struggler, which would make the whole demo say the opposite of the truth. So
the buyers here talk the way real buyers talk.

  northwind_1   Zara, won      textbook discovery; the Compounding Cost story
  northwind_2   Zara, won      price objection turned; multithreaded close
  kestrel_1     Zara, open     the Smoke Alarm reframe; strong qualification
  halcyon_1     Bilal, lost    a single unbroken feature monologue over 3 min
  halcyon_2     Bilal, lost    price objection met with a discount reflex
  brightline_1  Bilal, open    improving, but the next step is one-sided
  orbit_1       Daniyal, won   competent; a proof point lands
  tanner_1      Daniyal, lost  incumbent objection raised twice, never resolved
  vantage_1     Fatima, open   outstanding discovery, no close at all
  cobalt_1      Hina, open     newer rep, good instincts, thin qualification

Speaker labels are parsed by the offline transcriber: a line beginning REP maps
to speaker 0, anything else to speaker 1.
"""

from __future__ import annotations

SCRIPTS: dict[str, str] = {}


SCRIPTS["northwind_1_discovery"] = """\
REP: Morning Ayesha, thanks for making the time. I know you have a hard stop at half past, so I want to spend most of this on you rather than on me. Before I show you anything, can you walk me through how renewals actually move through Northwind today?
BUYER: Sure. So we have about four hundred contracts on the book, spread across three regions. The renewal dates live in a spreadsheet that our ops coordinator owns, and she is genuinely brilliant, she has been doing it five years. There is a shared inbox where the account managers get pinged when something is coming up in the next thirty days, and then it is on them to actually reach out. In theory that is fine. In practice it depends entirely on whether the ping gets seen, and the inbox has about four hundred other things in it at any given moment.
REP: Who owns that spreadsheet if the coordinator is out?
BUYER: Honestly, nobody, and that is exactly the problem. She was on annual leave for three weeks in November, and we did not really have a handover plan because it had never been a problem before. We found out in January that four renewals had gone past their notice period during that window. Nobody was being careless. There just was not a second person who knew to look.
REP: What happens when one goes past notice?
BUYER: It auto-renews at the old rate, so we lose the annual uplift entirely for that term. Or worse, the customer notices before we do and comes to us wanting to renegotiate, and now we are on the back foot in a conversation we should have been leading. We had one last year where the customer opened with a request for a fifteen percent reduction because they knew we had missed the window. We ended up flat. That is a good outcome in the circumstances but it is not the outcome we wanted.
REP: What is the uplift worth, roughly, per contract?
BUYER: It is normally six to eight percent on renewal. On an average contract that is somewhere around nine thousand a year, so call it thirty six over a four year relationship. And that compounds, because next year's uplift is calculated off this year's base. Missing one does not cost you nine thousand, it costs you nine thousand plus everything that would have stacked on top of it.
REP: So four missed in one quarter is somewhere north of thirty five thousand of immediate uplift, and considerably more over the life of those contracts. And that was one person taking annual leave.
BUYER: When you put it like that it sounds significantly worse than it feels day to day. I think that is the thing that gets me, actually. It never arrives as a crisis. There is no moment where somebody says we have lost thirty five thousand. It just quietly is not there at the end of the year and everyone assumes the market was soft.
REP: That is usually how it goes. Can I tell you about a team that had almost exactly this shape of problem?
BUYER: Go ahead.
REP: A freight business, a bit smaller than you, around three hundred contracts. Same setup, spreadsheet and an inbox. They were not losing renewals to competitors. They were losing them to nobody at all, which is the frustrating version, because there is nobody to beat and nothing to learn from. When they finally measured it, the losses clustered around holidays and handovers. Every gap in coverage cost them money about six weeks later, so nobody ever connected the two events. Once the renewal calendar stopped depending on one person remembering, their renewal rate went from eighty one to ninety four percent inside two quarters. None of that came from selling harder.
BUYER: Eighty one to ninety four is a big jump. I would want to understand what else changed for them, because that is a big enough number that I would assume something else was going on. Did they change their pricing, or their team, or anything structural?
REP: Fair challenge. They added no headcount and did not change pricing. What they did change was who could see what was coming. And I would not expect that jump from you, because your baseline is already better than theirs was. What I would expect is that the four you lost last quarter becomes zero. Does that feel like the right thing to aim at, or is there something bigger I am missing?
BUYER: No, that is the thing. That is genuinely the thing. If you had asked me what my top three problems were I might not have said this first, because it does not feel urgent. But if I am honest about where the money is going, it is this and it is not close. The rest of what I worry about is noise by comparison.
REP: Then let me ask the awkward question. If we found a way to make that true, who else would need to be comfortable before Northwind could actually move on it?
BUYER: Marcus would need to sign it off, he runs commercial and anything over fifty thousand is his call. And I would want our head of ops to look at it properly, because she is the one who would actually live in it every day. I have made the mistake before of buying something the team did not want, and it sat there. I am not doing that again.
REP: What would Marcus need to see? Is he a business case person or a risk person?
BUYER: Business case, firmly. He will want the number and he will want to know where the number came from. He is very good at spotting when an assumption has been chosen to make a total look better than it is, so I would not round anything up in front of him.
REP: Then let me build it on your four hundred contracts and your own uplift percentage rather than a generic model. Can we get you, me and Marcus on a call the week after next, and I will bring that?
BUYER: That works. Tuesday the fourth is probably best for him, he blocks Mondays for internal reviews and by Wednesday he is usually travelling. Let us say the fourth, and I will make sure he has actually read whatever you send beforehand rather than opening it in the meeting.
REP: Tuesday the fourth. I will send an invite this afternoon with a one page summary so he can come in cold and still follow it. Anything I should not say in front of him?
BUYER: Do not lead with the software. Lead with the thirty five thousand.
REP: Understood. Thanks Ayesha, this was genuinely useful.
"""


SCRIPTS["northwind_2_pricing"] = """\
REP: Thanks both. Marcus, Ayesha will have given you the short version, but I would rather you heard the number from your own data than from me. Can I put the model up?
BUYER: Please do. And I will say up front so we do not waste each other's time, I am sceptical about platforms generally. We have bought two in three years that nobody uses. One of them we are still paying for. So the bar here is not whether the product is good, it is whether it changes what people actually do on a Tuesday.
REP: That is fair, and I would rather hear it now than in six months. What happened with those two?
BUYER: Both the same story, more or less. They were sold to me, I got excited, we rolled them out to a team that had not asked for anything, and within about four months everyone had drifted back to what they were doing before. The tooling was fine. The problem was that nobody had established what it was replacing, so it became an extra thing rather than a different thing. That is on me as much as the vendors.
REP: Then let me be careful about how I answer the rest of this, because I do not want to be the third. On the model: four hundred contracts, average uplift seven percent, average value roughly one hundred and thirty thousand. Four missed renewals last quarter, which at your own numbers is about thirty six thousand of uplift gone.
BUYER: That number is roughly right. I would want to look at whether last quarter was typical before I annualise it, because November is genuinely our worst month for coverage and it may be flattering the case. But even if you halve it, it is not a small number.
REP: Halve it and it is seventy two thousand a year. The platform is fifty two.
BUYER: Which is still a lot for what is, at some level, a spreadsheet replacement. Honestly, that price is high for us. We are not a huge business and fifty two thousand of committed annual spend is a real decision, not a rounding error.
REP: Compared to what, though? Genuinely, I want to know what you are comparing it to, because that changes my answer.
BUYER: Compared to hiring another coordinator. Fully loaded that is about forty thousand, and I get a person who can do other things when renewals are quiet. That is the alternative that keeps occurring to me and I have not been able to talk myself out of it.
REP: That is a good comparison and I am not going to dismiss it. Can I push on it for a second? The coordinator you have is excellent, and the four you lost were lost while she was doing her job well, because she was on leave. A second coordinator halves that risk. It does not remove it, and it adds a handover between two people.
BUYER: No, that is fair, and the handover is genuinely where things go wrong for us. We have seen that in other parts of the business. Two people covering something is often worse than one, because each assumes the other has it. I had not thought about it in those terms but you are right that hiring does not actually solve the failure mode I described, it just makes it less frequent.
REP: So the way I would frame it, and you should push back if this is convenient reasoning on my part, is that the coordinator is forty thousand to reduce the risk, and this is fifty two to remove the dependency on anyone remembering at all. If it recovers even two of the four, it has paid for itself, and you still have your coordinator doing the work she was actually hired for.
BUYER: Two of four is not a high bar. That is the part that makes this difficult to argue against, and I notice I am looking for a reason to say no rather than evaluating it. Let me ask Ayesha something instead. Would the ops team actually use this, or am I about to buy platform number three?
BUYER: They would use it if it replaced the spreadsheet rather than sitting next to it. That is the whole thing for me. If in three months both exist, we have failed, and I would want to be able to say that out loud rather than pretending it is going fine.
REP: Then that is the condition I would want written into the rollout. If ninety days in the spreadsheet still exists, we have failed, and you should tell us so.
BUYER: I would like that in writing, not as a handshake. Put it in the contract as a success criterion and I will take this to procurement on Monday.
REP: I will put it in the proposal as a success criterion rather than a footnote. Marcus, what is the process from there on your side?
BUYER: Legal and procurement together, about two weeks if nothing is contentious. I can start that in parallel with the commercial conversation if we are broadly agreed on the number, which I think we are. The one thing I will not do is compress legal, so if you need this signed by month end that is not going to happen and I would rather say so now.
REP: Understood, and I would rather have it right than fast. Can I send the proposal tomorrow morning, and can you and I speak Friday to close out any changes so procurement starts Monday?
BUYER: Friday morning works. Ayesha, you should be on that too.
REP: I will send the invite for Friday at ten and the proposal by nine tomorrow. Thank you both.
"""


SCRIPTS["kestrel_1_discovery"] = """\
REP: Tomas, thanks for the time. You reached out to us rather than the other way round, which is unusual, so before I assume anything, what made you pick up the phone?
BUYER: We missed a renewal in December that we absolutely should not have missed. Eighty thousand euro, one of our older accounts, the kind of customer you assume will always be there. My board asked me how it happened and I did not have a good answer, which was worse than the eighty thousand honestly. I have been in this job four years and that was the first time I could not explain something to them.
REP: That is a specific and quite painful reason. What was the actual failure? Was it a system thing or a people thing?
BUYER: Both, and I think that is what makes it hard to fix. The account manager who owned it left us in October. His accounts were reassigned within a week, which felt fast at the time. But his calendar was not reassigned, and neither was anything he kept in his own head about which customers needed an early conversation. So on paper the account had an owner. In reality nobody had ever spoken to that customer about their renewal and the new owner did not know it was coming.
REP: So the information existed, it just did not travel with the account.
BUYER: Exactly that, and I suspect it is still true for a lot of our book. That is the part that worries me more than the eighty thousand. December was the one we found out about.
REP: Can I offer you a way of thinking about this that our better customers use? I find it clarifies where the money actually leaks.
BUYER: Please.
REP: Most teams treat a renewal as a calendar entry. A date arrives, somebody acts. But a renewal behaves much more like a smoke alarm than a calendar entry. A calendar entry works as long as someone is looking at the calendar. A smoke alarm works precisely because nobody has to remember it exists. The reason your December renewal went is not that the date was wrong. It is that the date was only ever going to be seen by one particular person, and that person left. Every process that depends on a specific human noticing is a calendar entry wearing a smoke alarm costume.
BUYER: That is uncomfortably accurate, and I am going to steal it for my board. It also explains why our instinct after December was wrong. We responded by telling everyone to be more careful, which is the classic useless response. Being more careful is just adding more calendar entries.
REP: How many other accounts are currently in that state, where the knowledge sits with one person?
BUYER: I genuinely do not know, and that is the honest answer. If you asked me to guess I would say a third, but I would not defend the number. We have about two hundred and sixty accounts. We have had four people leave in eighteen months, which is not unusual for our sector, and I could not tell you what happened to the knowledge in any of those handovers.
REP: And what does a typical account renew at?
BUYER: Forty to ninety thousand euro. Call it sixty as an average, though the distribution is lumpy, we have a dozen that are much larger and they are the ones I lose sleep over.
REP: So a single miss is roughly the cost of this platform for a year. I say that not as a closing line, but because it means the business case here is not really about efficiency. It is about not repeating December.
BUYER: That is precisely how the board will see it, and it is how I see it. I am not looking for productivity. I am looking to be able to answer the question if it happens again.
REP: Who else would need to be convinced, and what would convince them?
BUYER: Our CFO, primarily. She is rigorous and she will want to know what happens if we do nothing, expressed as a number. She will not accept a vendor estimate for that, and she should not, she has seen a lot of vendor estimates. She will also ask why we cannot solve it with process, and I need a better answer than the one I currently have.
REP: She should not accept our estimate. Would she accept your own December number, with the notice periods across your two hundred and sixty accounts mapped out so she can see how many are currently unowned?
BUYER: That she would take seriously, because it is our data and she can check it. If it turns out only a handful are exposed then she is right and I am worrying about nothing.
REP: Then let me not send you a demo. Let me send you a short template you fill in from your own CRM export, and we look at the output together. If it turns out three accounts are exposed, you do not have a problem worth fifty thousand and I will tell you that.
BUYER: You would actually tell me that? I ask because most people in your position would find a way to make three accounts sound alarming.
REP: I would rather lose this now than in month four. Can we look at it together on the eighteenth?
BUYER: The eighteenth works. Send the template.
REP: Going out today. Thanks Tomas.
"""


SCRIPTS["halcyon_1_demo"] = """\
REP: Hi Doctor Oyelaran, thanks for taking the time. Let me jump straight in and walk you through the platform.
BUYER: Alright.
REP: So Cadence is a full revenue operations platform, and the way I usually structure this is to go module by module so you get the complete picture. The core of it is the unified dashboard, which brings together renewals, expansions and churn risk in a single view, and you can slice that by team, by region, by product line, by account tier, or by any custom field you define during setup. Underneath that we have real time alerting, which is fully configurable, so you can route alerts by severity, by owner, by schedule, or by a combination of all three, and there is an escalation ladder if the first owner does not acknowledge within a window you define, and that window is itself configurable per alert type. We also ship a complete audit trail, so every change to a contract record is logged with the actor, the timestamp, and the before and after values, which our regulated customers tell us is essential for their compliance reviews, and that log is exportable in three formats.
REP: On the reporting side there is a custom report builder with about sixty prebuilt templates covering the standard revenue operations questions, and you can schedule any report to land in an inbox or a messaging channel on whatever cadence you choose, daily, weekly, monthly or on a custom cron expression. There is role based access control with granular permissions down to the individual field level, single sign-on with all the major identity providers, SCIM provisioning so your directory stays in sync automatically, and an open REST API plus outbound webhooks for anything we have not thought of. We have native integrations with around forty tools at this point, including the big CRMs, the main ticketing systems, most of the finance stack, and a growing number of data warehouses. The mobile applications are on both platforms and they are genuinely full featured rather than read only, so an account manager can action a renewal from a client site without waiting to get back to a laptop.
REP: On top of all of that there is an analytics layer with cohort analysis, retention curves, net revenue retention tracking, and a forecasting module shipping next quarter that will project renewals four quarters out with confidence intervals derived from your own historical close rates. Most of our customers tell us the dashboard alone saves them several hours a week per account manager, and the alerting is what stops things falling through the cracks entirely. Everything is configurable, so you only see what is relevant to your team, we can turn modules off entirely if you do not need them, and the onboarding team handles all of the configuration for you during implementation, which typically runs four to six weeks depending on how many integrations you want live on day one. We also assign a dedicated customer success manager for the first ninety days who runs weekly check-ins, and there is a full library of training material plus live sessions every fortnight for new users.
BUYER: It is a lot.
REP: It is comprehensive, yes, and I appreciate that can feel like a lot in one sitting. The good news is you would never see all of it at once. Most teams start with the dashboard and alerting, and then grow into the reporting and analytics over the first six months as they find questions they want answered. The forecasting module is the one people get most excited about once they have a few quarters of clean data in the system, because that is when it starts being genuinely predictive rather than just descriptive.
BUYER: Can I ask what problem you think we have?
REP: Well, most organisations in your space are dealing with renewal visibility and manual processes, so that is usually where we start, and the dashboard tends to be the thing that makes the difference.
BUYER: Right. The reason I ask is that we are a hundred and eighty people and we run about ninety contracts. I have been sitting here trying to map what you are describing onto anything we actually do, and I am struggling. You have shown me a platform that looks like it was built for someone with two thousand accounts and a revenue operations team. We do not have a revenue operations team. We have me, two account managers, and a finance director who does this alongside four other things.
REP: We work with organisations of all sizes and the pricing does scale down. The configurability means you can strip it back to just what you need.
BUYER: Okay.
REP: Would you like me to show you the alerting configuration? That is usually the part people find most impressive.
BUYER: Not especially, no.
REP: Should I send over some materials and we can pick this up next week?
BUYER: Sure, send them over.
"""


SCRIPTS["halcyon_2_pricing"] = """\
REP: Hi again. Did you get a chance to look at the materials I sent?
BUYER: I skimmed them, and I shared the pricing page with my finance director. I will be honest that neither of us got very far past the first number.
REP: Sure. So as you saw, the standard tier comes in at ninety four thousand a year for your seat count, and that includes onboarding, the integration work and support.
BUYER: That is well beyond what we were expecting, and I do not think it is a negotiating position to say so. For context, our entire software budget across the organisation is about two hundred thousand. You are asking for nearly half of it for something that manages ninety contracts.
REP: I hear you, and I do have some flexibility there. I could probably get you to eighty five, maybe eighty if we were able to sign this quarter.
BUYER: It is not really about finding another ten thousand.
REP: We could also look at a two year term, which brings the annual number down further, closer to seventy five, and that also locks your rate against uplift for the second year, so there is a hedge in it as well.
BUYER: I do not think you are hearing me, and I want to be straightforward rather than let this run on. The issue is not the number. It is that after two conversations I still cannot tell you what this would do for us. My finance director asked me a very simple question, which was what would we stop doing if we bought this, and I did not have an answer. Not a weak answer. No answer at all.
REP: Right. Well, the platform automates a lot of the manual renewal tracking, so the time savings there are significant. Most customers see several hours a week back per account manager.
BUYER: We have two account managers and neither of them has ever told me they are short of time. If I went to them and said I have bought you something that saves you three hours a week, they would ask me what I wanted them to do with it. That is not a problem we have. Our problem, if you had asked, is that we win about half the renewals we should and I do not know why.
REP: There is also the visibility piece, and the reporting, which a lot of leadership teams find valuable for board reporting.
BUYER: We are not short of reports either. I have more reports than I read.
REP: I could put together a business case document if that would help frame it?
BUYER: Built on what, though? You have not asked me a single question about how we actually run renewals. Not one, across two calls. You could not write a business case for us because you do not know anything about us. I do not say that to be unkind, but I think we should stop here rather than have a third conversation.
REP: That is fair. What does the process look like at the moment?
BUYER: I do not think we are at the stage where that is a useful question any more. I think we are going to stay where we are for now.
REP: Would it help if I got my solutions engineer on a call? He is very good at the technical detail.
BUYER: No, thank you. I appreciate your time.
REP: Alright. I will check back in a quarter or so in case things change.
BUYER: Sure.
"""


SCRIPTS["brightline_1_scoping"] = """\
REP: Owen, thanks for the time. I want to scope the pilot properly today rather than demo at you.
BUYER: Good, because the last call was a lot. I came away knowing a great deal about your product and I am not sure you came away knowing anything about us. I say that in a friendly way, but if we are going to spend money together I would rather be direct about it.
REP: That is fair feedback and I will take it. Let me start somewhere more useful. What is the thing that would make you say the pilot worked?
BUYER: If we stopped finding out about renewals from the customer. That is the embarrassing one. Right now, more often than I would like, a customer emails us asking what happens next, and we have to pretend we were about to get in touch. It undermines the relationship in a way that is hard to measure but I can feel it. It also means we are always reacting rather than setting the terms.
REP: How often does that happen at the moment?
BUYER: Maybe once a month, sometimes twice. Out of roughly a hundred and forty accounts, so it is not an epidemic, but it is consistent, and the ones it happens to tend to be the mid-sized accounts that nobody has quite claimed. The big ones get attention because they are big. The small ones we barely touch anyway. It is the middle that goes quiet.
REP: That is a good measurable. Once a month going to zero. What is the current process, so I know what we would be replacing rather than adding to?
BUYER: There is not really a process, which is the honest answer. The account managers each keep their own tracker. There is no central one and there never has been. One of them uses a spreadsheet, one uses the calendar in her email client, and one of them, and I am not joking about this, uses a paper diary. He is our best performer, which makes it very difficult for me to tell him to stop.
REP: I believe you, we see it more often than you would think. Let me describe how the pilot would run and you tell me where it breaks. We would take one team, not the whole company, import their accounts, and run in parallel with the existing trackers for six weeks. If at the end of six weeks the paper diary is still being used, we have not earned the rollout.
BUYER: I like that it is one team, and I like that the failure condition is concrete. Which team would you pick, though? Because that choice is going to determine the result more than anything in your product.
REP: I would pick whichever has the most renewals in the window, because that is where we find out fastest. But you know your people better than I do. Is there a team where the pilot would fail for political reasons rather than product ones?
BUYER: The northern team would resist anything new right now. They have had a genuinely rough quarter, they are two people down, and if I put a new tool in front of them it would be received as a criticism rather than as help. That is not about you. The central team would be fine, and their lead actually asked me for something like this about six months ago, so there is some appetite there already.
REP: Then central, and their lead should be the one who declares it a success or not, rather than me.
BUYER: That is sensible, and it also solves a problem for me, because if it comes from her the rest of the business will take it more seriously than if it comes from me. What does the pilot cost?
REP: Twelve thousand for the six weeks, credited in full against the annual contract if you proceed. If you do not, you keep the configuration export and we part company.
BUYER: I would need to run that past finance but it is not an outrageous number and I do not think it will be the blocker. The blocker, if there is one, will be timing. We are into our busiest period from the middle of April, and starting something new in the middle of that would guarantee it fails.
REP: Then let us not start it in April. Anything else that would stop this?
BUYER: Not that I can think of right now.
REP: Good. I will write up the pilot scope with the success criterion we agreed, the team, and the credit terms, and get that over to you this week.
BUYER: Thanks.
REP: Speak soon.
"""


SCRIPTS["orbit_1_expansion"] = """\
REP: Priya, Sam, thanks for making time. You have been on the platform eight months now, so I mostly want to know what is working and what is not before we talk about anything else.
BUYER: Broadly it is working, and I would not have said that at month two. The alerting is the thing the team would genuinely not give up now. We went from finding out about renewals late to having a fairly boring, predictable rhythm, which is exactly what you want from this kind of thing. Boring is the goal.
REP: Good. And the parts that are not?
BUYER: Reporting, and specifically the board pack. We still export everything and rebuild it by hand every month, which feels absurd given all the data is already sitting in your system. Sam owns that and I think he would say it is the worst week of his month.
BUYER: It is. It is genuinely the worst week of my month. It is not that any individual step is hard, it is that there are about thirty of them and they all have to happen in order, and if one number changes upstream I have to redo half of it. Then I spend a day chasing regional leads for commentary that they were supposed to send me a week earlier.
REP: How long does it take, end to end?
BUYER: Half a day if everything goes well, which it never does. Closer to a full day once you count the chasing, and that is a day where I do nothing else. Over a year that is twelve working days assembling a document out of data we already have.
REP: Is that worth solving, though? I ask because the board pack module is the thing I would most want to show you today, and I would rather not show it if a day a month is something you have made peace with.
BUYER: It is worth solving. It always lands in the worst week of the month, and it is the reason I work the weekend before the board meeting. If you can genuinely take that away I would be very interested. I am slightly wary because we were told the standard reporting would handle it and it did not.
REP: That is a fair thing to hold against us. Let me show you the two things this does differently and you can tell me if they cover your pack. First, it pulls the renewal and expansion numbers directly, so there is no export step at all. Second, and this is the part people react to, it keeps last month's commentary alongside this month's numbers, so you are editing rather than starting from a blank page.
BUYER: The commentary carrying over is the bit that would actually save the day. Ninety percent of what I write is the same as last month with the numbers changed and one paragraph about whatever went wrong. Starting from blank every time is what makes it take a day.
REP: That is what we hear consistently. One of our customers, a distribution business roughly your size, measured it properly before and after. Their pack went from a day and a half to about ninety minutes, and the person who owned it stopped dreading month end, which was the part their leadership actually cared about. I would not promise you ninety minutes, but I would be surprised if you did not halve it.
BUYER: What does it cost to add?
REP: Eighteen thousand on top of your current contract, and it renews on the same date so you are not managing two cycles.
BUYER: That is reasonable, and it is under my approval limit which makes life easier. Sam, would you actually use it, or is this me buying you something you did not ask for?
BUYER: I would use it, yes, provided it handles the regional split properly. Our pack breaks out four regions and each one has a different set of product lines, and most tools I have seen assume a single flat structure. If I have to rebuild the regional view by hand then I have saved nothing.
REP: It does handle it, and I would rather prove that than assert it. Can I enable the module on your own data for two weeks, and Sam builds next month's pack in it? If the regional split does not work, we drop it and I have wasted only my own time.
BUYER: That is a good offer and I will take it. Let us do that.
REP: I will have it enabled by Thursday and send Sam a fifteen minute walkthrough so he is not figuring it out alone. Priya, can we speak the week after the pack goes out to decide?
BUYER: Yes, put something in for the twelfth.
REP: Twelfth it is. Thanks both.
"""


SCRIPTS["tanner_1_evaluation"] = """\
REP: Henrik, thanks for the time. I know you are evaluating a few options, so what would be most useful to cover?
BUYER: Honestly, the main thing is why we would move off what we have. We already use Sentinel, we have used it for three years, and it mostly works. I am not in this conversation because I am unhappy. I am in it because my board asked me to look at the market, and I would rather do that properly than tick a box. So the burden of proof is genuinely on you here and I do not want to pretend otherwise.
REP: That is the right question to be asking. What does mostly working mean in practice?
BUYER: It does the tracking fine, no complaints there. The reporting looks like it was designed in about two thousand and twelve and has not been touched since, and their support is slow, days rather than hours. But it does not go down, it does not lose data, and the team knows how to use it. Those three things cover most of what I need from a system like this.
REP: Understood. Let me show you where we are different, and you can judge whether the difference is worth a migration, because migrations are genuinely painful and I am not going to pretend otherwise.
BUYER: Go on.
REP: The reporting is the clearest gap. Our builder is drag and drop, and reports refresh live rather than overnight. Support is a named engineer rather than a queue, with a four hour response on the tier you would be on.
BUYER: Four hours is better, no argument. But here is where I get stuck, and I got stuck in the same place with the other vendor I spoke to. We have three years of history in Sentinel. Contracts, dates, owners, and crucially about eleven thousand notes attached to accounts. Those notes are where the actual institutional knowledge lives. When someone says this customer always pushes back on the March invoice, that is in a note, not in a field. I do not understand how that moves.
REP: We have an importer built specifically for Sentinel. It carries contracts, dates and owners across cleanly.
BUYER: What about the notes, though? That is the part I asked about.
REP: The notes come across as attachments on the contract record.
BUYER: Attachments is not the same as searchable, and I think you know that. If I have to open a file to find out what we said to a customer in twenty twenty four, nobody will do it, and three years of knowledge effectively evaporates on the day we migrate. That is not a small consideration. That might be the whole consideration.
REP: Let me show you the alerting instead, because that is the other significant difference and I think it is where the day to day improvement is.
BUYER: Sure, although I would like to come back to the notes.
REP: You can route by severity and by schedule, so out of hours goes to a different owner, and escalation ladders are built in rather than bolted on.
BUYER: Sentinel does that too, to be fair to them. Not as flexibly, from what you are showing me, but the gap is not large enough to justify a migration on its own.
REP: Ours is more flexible in how the ladders are configured, and you can nest conditions.
BUYER: Maybe. Look, I will be straight with you because I think it is more useful than being polite. The team is not unhappy with Sentinel. To move, I would need something that made the last three years come with us properly, and searchable notes is a real part of that, not a nice to have. Everything else you have shown me is better, but better is not the same as worth the disruption.
REP: I understand. I will find out what our options are on notes and come back to you.
BUYER: Do that, but I would not want you to spend a lot of time on it if the answer is no.
REP: Would it help if I sent over the migration guide in the meantime?
BUYER: You can send it. I cannot promise I will read it closely.
REP: Understood. I will follow up next week.
BUYER: Thanks.
"""


SCRIPTS["vantage_1_discovery"] = """\
REP: Grace, thank you for the time. I have done a bit of reading but I would rather hear it from you. How does the renewal side of Vantage actually run today?
BUYER: We have two people on it full time and about six hundred contracts, mostly grocery and food service, split fairly evenly. The two of them are good and they have been doing it a while, so there is a lot of judgement in how they work that is not written down anywhere. They work off a list of what is due in the next sixty days, which they pull manually every Monday morning, and then they work through it in whatever order feels most urgent.
REP: What falls off that list?
BUYER: Anything beyond sixty days is effectively invisible until it enters the window, so we never get ahead of anything. And the small contracts get deprioritised constantly, which is a problem because there are a lot of them and collectively they are not small. If you have a ninety thousand renewal and a nine thousand renewal in the same week, the nine thousand one loses every single time, and everyone involved thinks that is the right call. Individually it is. In aggregate I am not sure it is.
REP: How small is small, in your terms?
BUYER: Under fifteen thousand. That is maybe two hundred of the six hundred, so a third of the book by count. By value it is more like twelve percent, which is how it has always been justified internally. But twelve percent of our revenue is not nothing, and I suspect the churn in that segment is considerably worse than the segment we look after properly.
REP: What is the renewal rate on those compared to the larger ones?
BUYER: I would have to check, and the fact that I would have to check is probably itself the answer. My instinct is that it is noticeably worse, maybe eight or ten points. Nobody has ever put the two numbers side by side, partly because the reporting does not make it easy and partly, I think, because nobody wants to know.
REP: That guess is worth checking, because if it is even five points worse across two hundred contracts averaging ten thousand, that is a hundred thousand a year sitting in the part of the book that nobody has time for.
BUYER: That is a genuinely uncomfortable calculation and I am going to run it this week regardless of where this conversation goes. If it is ten points it is two hundred thousand, which is more than the two people cost us.
REP: What would need to change for that third of the book to get the same treatment as the top?
BUYER: We would need a way to handle them without adding headcount, because there is no headcount and there will not be any this year. That is not a negotiating position, it is a hiring freeze. So any answer that starts with hire someone is not an answer for us.
REP: Understood. Is there appetite to treat them differently rather than the same? A lot of teams find the small contracts do not need a person, they need a sequence.
BUYER: What do you mean by a sequence?
REP: A defined set of touches that go out on a schedule, with a human stepping in only on exception. The person stops doing two hundred renewals and starts handling the fifteen that go sideways.
BUYER: That would work if the exception logic were genuinely reliable, and that is where I would want to spend all of my scepticism. If we still have to check everything to make sure the automation did not miss something, then nothing is saved and we have added a system. I have seen that happen. The tool becomes another thing to audit.
REP: Agreed, and the exception logic is the thing I would want you to interrogate hardest rather than take on faith. What else is on your mind?
BUYER: Whether our data is clean enough for any of this to work. About half the contracts came in through an acquisition eighteen months ago and the records are genuinely inconsistent. Different date formats, some missing owners, a handful of duplicates we know about and probably more we do not. Every project we have started in the last year has run aground on that.
REP: How bad, if you had to characterise it?
BUYER: Bad enough that I would not want to promise you it can be fixed in a fortnight. Not so bad that it is hopeless. Probably three or four weeks of someone's attention, and the someone would realistically be me, because I am the only person who knows both sets of conventions.
REP: Then the plan has to respect your time or it will not happen, and I would rather build that in than discover it in week three. What does your quarter look like?
BUYER: Busy until the end of March, genuinely. April is more open.
REP: That is useful to know. Anything else I should understand before I go away and think about this?
BUYER: No, I think you have most of it. This was a good conversation, actually. Most people just demo at me for forty minutes.
REP: I appreciate that. I will have a think and put something together.
BUYER: Great, thanks.
REP: Thanks Grace.
"""


SCRIPTS["cobalt_1_intro"] = """\
REP: Hi Rachel, thanks for taking the call. I appreciate you fitting me in.
BUYER: No problem, I have about twenty five minutes before my next thing.
REP: That is plenty. Can I start by asking what made you take the meeting? I would rather know that than guess.
BUYER: We are growing quickly and the way we handle renewals has not grown with us. Two years ago we had sixty accounts and one person could genuinely hold all of it in her head, and she did, brilliantly. We have just over two hundred now and she still tries to, which is both impressive and completely unsustainable. I do not think she would tell you she is struggling, which is part of what worries me.
REP: What has actually gone wrong so far, if anything?
BUYER: Nothing catastrophic yet, and I want to be honest about that rather than manufacture urgency. A few late ones, a couple of renewals where we got to the customer with about a week to spare and had to rush a conversation that should have taken a month. No losses that I can attribute directly to it. But it feels fragile in a way it did not eighteen months ago, and I have learned to pay attention to that feeling.
REP: Fragile is the right word, and it is usually the honest signal before something breaks. What would have to happen for this to become urgent rather than important?
BUYER: If she left, frankly. That is the whole risk in one sentence. She has been with us six years, she is not going anywhere as far as I know, and I would be in genuine trouble within a fortnight. There is no documentation. There is no second person. If she resigned tomorrow I would not be able to tell you which accounts were up for renewal in April.
REP: So part of what you would be buying, if you bought anything, is that the knowledge stops living in one person.
BUYER: Yes, and I had not framed it that way until you said it. I have been thinking about this as an efficiency problem and it is not, it is a continuity problem. Those have quite different price tags in my head.
REP: What have you looked at so far?
BUYER: Nothing seriously, you are the first conversation. I did an hour of searching last month and got overwhelmed by how similar everything looked, so I stopped.
REP: Then I will not oversell. Broadly there are three ways teams solve this. Hire a second person, build something internally on top of your CRM, or use a platform like ours. All three genuinely work. Which is right depends on whether your real constraint is money, engineering time, or speed.
BUYER: Engineering time, definitely, and it is not close. We have a small team and a long roadmap, and an internal tool for the renewals process would never get prioritised above customer facing work. It would get agreed in principle and then sit in the backlog for a year. I have watched that happen twice.
REP: Then internal build is out, which leaves headcount or a platform. Would it be useful if I laid out honestly what each of those costs you over two years, including the parts that are not the invoice?
BUYER: That would be genuinely helpful, yes, and I would rather have that than a demo at this stage.
REP: I will do that. Can I also ask what your budget process looks like? I do not want to build something you cannot act on.
BUYER: Anything over forty thousand goes to our managing director. Below that I can sign it myself, though I would still talk to him about something that changes how a whole function works.
REP: Is he someone who buys on risk or on return?
BUYER: Risk, without question. He worries about single points of failure more than almost anything else, it is a bit of a theme with him. If you frame this as efficiency he will be lukewarm. If you frame it as what happens when she leaves, you will have his full attention.
REP: That is helpful, because that is also the strongest and most honest version of the argument. Let me put the comparison together and send it over. Would it make sense to talk again once you have read it?
BUYER: Yes, send it and we will find some time.
REP: I will get it over by Wednesday. Thanks Rachel.
BUYER: Thank you.
"""


def get(name: str) -> str:
    if name not in SCRIPTS:
        raise KeyError(f"unknown seed script: {name}")
    return SCRIPTS[name]


def talk_balance(name: str) -> float:
    """Rep share of words in a script.

    Used by the seed tests to keep the corpus honest: if an edit tips the top
    performer above the struggler, the demo would start telling the opposite of
    the truth, and that should fail a test rather than be noticed on stage.
    """
    rep = buyer = 0
    for line in get(name).splitlines():
        if ":" not in line:
            continue
        speaker, text = line.split(":", 1)
        words = len(text.split())
        if speaker.strip().upper().startswith("REP"):
            rep += words
        else:
            buyer += words
    total = rep + buyer
    return round(rep / total, 3) if total else 0.0
