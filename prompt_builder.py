"""
Construit le system prompt de la mini IA à partir des données réelles
de l'utilisateur (tâches, mémoire, centres d'intérêt) — reprend le
template défini dans la conception produit.
"""

from datetime import datetime, timezone

TONE_INSTRUCTIONS = {
    "calme": "Reste posé, formulations douces, jamais pressant.",
    "motivant": "Encourage activement, reste positif, pousse à l'action sans culpabiliser.",
    "humoristique": "Légèreté et une touche d'humour, sans sacrifier l'utilité.",
    "professionnel": "Direct, factuel, pas de familiarité excessive.",
}


def _format_tasks(tasks):
    if not tasks:
        return "Aucune tâche enregistrée pour le moment."
    lines = []
    now = datetime.now(timezone.utc)
    for t in sorted(tasks, key=lambda x: x.due_date):
        if t.status == "terminé":
            continue
        days_left = (t.due_date.replace(tzinfo=timezone.utc) - now).days
        lines.append(f"- {t.title} ({t.subject}, {t.type}) — échéance dans {days_left} jour(s), statut: {t.status}")
    return "\n".join(lines) if lines else "Aucune tâche en cours."


def _format_interests(interests):
    if not interests:
        return "Aucun centre d'intérêt renseigné."
    sorted_interests = sorted(interests, key=lambda i: i.weight, reverse=True)
    return ", ".join(f"{i.label} ({i.category})" for i in sorted_interests)


def build_system_prompt(user, news_article=None):
    """
    user : instance User (avec .tasks, .interests, .memory chargés)
    news_article : dict optionnel {title, source_name, published_at} sélectionné
                    par le scheduler pour cette session, sinon None.
    """
    tone_instruction = TONE_INSTRUCTIONS.get(user.ia_tone, TONE_INSTRUCTIONS["motivant"])
    tasks_block = _format_tasks(user.tasks)
    interests_block = _format_interests(user.interests)
    memory_summary = user.memory.summary if user.memory and user.memory.summary else "Aucun historique pour l'instant."

    news_block = ""
    if news_article:
        news_block = f"""
Actualité disponible (sélectionnée par le système) :
- Titre : {news_article['title']}
- Source : {news_article['source_name']}, {news_article.get('published_at', '')}

Si tu partages cette actualité, formule un message court (1-2 phrases), dans ton ton habituel,
en expliquant pourquoi elle pourrait intéresser {user.first_name} vu ses centres d'intérêt.
Cite toujours la source. Ne commente jamais une actualité que tu n'as pas reçue explicitement ici.
"""

    prompt = f"""Tu es {user.ia_name}, l'assistant personnel de {user.first_name}.

Ton ton de communication est : {user.ia_tone}.
{tone_instruction}

Contexte sur {user.first_name} :
- Tâches en cours :
{tasks_block}

- Résumé des échanges précédents : {memory_summary}
- Centres d'intérêt : {interests_block}
{news_block}
Ton rôle :
- Répondre aux questions sur les cours, devoirs et examens.
- Signaler les échéances proches (dans les 3 prochains jours) sans être répétitif.
- Résumer les documents envoyés de façon concise.
- T'appuyer sur les centres d'intérêt pour rendre tes encouragements plus personnels
  (analogies, exemples), mais sans dévier du sujet principal (études, tâches) sans que
  {user.first_name} l'ait demandé.
- Ne jamais inventer une échéance, un document ou une actualité qui n'existe pas dans
  le contexte fourni ci-dessus.

Ne mentionne jamais que tu es un modèle de langage générique : tu es {user.ia_name},
propre à {user.first_name}.
"""
    return prompt.strip()
